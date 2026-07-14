# -*- coding: utf-8 -*-
"""
Engine de inferência para detecção de objetos.
"""

import time
from pathlib import Path
from threading import Lock
from typing import Optional, Dict, Any, List

import numpy as np
import torch
from PIL import Image
from PySide6.QtCore import QObject, Signal, QThread, QMutex, QWaitCondition

from config import get_settings
from core.logger import get_logger
from core.metrics import MetricsCollector
from core.exceptions import InferenceError

from .model_loader import ModelLoader, TASK_INSTANCE_SEGMENTATION
from .postprocess import PostProcessor
from .segmentation_postprocess import SegmentationPostProcessor
from .events import DetectionResult, DetectionEvent

logger = get_logger("detection.engine")


class InferenceWorker(QThread):
    """
    Thread de inferência.
    
    Signals:
        detection_ready: Emitido quando uma detecção está pronta
        error_occurred: Emitido em caso de erro
    """
    
    detection_ready = Signal(object)  # DetectionResult
    error_occurred = Signal(str)
    
    def __init__(
        self,
        model: Any,
        processor: Any,
        postprocessor: PostProcessor,
        device: str,
        target_fps: float = 15.0,
        diagnostic_log_interval: int = 25,
        diagnostic_dump_dir: Optional[str] = None,
    ):
        super().__init__()
        
        self._model = model
        self._processor = processor
        self._postprocessor = postprocessor
        self._device = device
        self._target_fps = target_fps
        # A cada N frames, emite um log INFO de diagnóstico mesmo que não
        # haja detecções, para que o operador veja o que o modelo "vê".
        self._diagnostic_log_interval = max(1, int(diagnostic_log_interval))
        # Diretório opcional para salvar UMA amostra de frame quando o
        # diagnóstico aciona WARNING (ajuda a verificar visualmente se a
        # câmera está enviando uma imagem válida — preto, saturada, etc.).
        self._diagnostic_dump_dir: Optional[Path] = (
            Path(diagnostic_dump_dir) if diagnostic_dump_dir else None
        )
        self._dumped_diagnostic_sample = False
        
        self._running = False
        self._paused = False
        self._current_frame: Optional[np.ndarray] = None
        self._frame_id = 0
        
        self._mutex = QMutex()
        self._pause_condition = QWaitCondition()
        self._frame_condition = QWaitCondition()

        # Estatísticas agregadas para diagnóstico.
        self._frames_processed = 0
        self._frames_with_detection = 0
        self._frames_with_segments_above_threshold = 0
        self._frames_rejected_by_class = 0
        self._sum_inference_ms = 0.0
        self._max_query_score_seen = 0.0
        self._last_diagnostic_log_frame = 0
        # Estatísticas do conteúdo do frame (em uint8 BGR) para detectar
        # imagens pretas/saturadas/sem variação que silenciosamente fariam
        # a inferência produzir scores ínfimos.
        self._sum_frame_mean = 0.0
        self._sum_frame_std = 0.0
        self._min_frame_mean = float("inf")
        self._max_frame_mean = 0.0
        # Conta apenas frames cujo conteúdo foi efetivamente medido (não
        # confundir com `_frames_processed`, que conta resultados de inferência;
        # em testes unitários, frames podem não ser passados).
        self._frame_stat_count = 0
        # Cache da última amostra para potencial dump diagnóstico.
        self._last_sample_frame: Optional[np.ndarray] = None
        # Hashes (CRC32) dos frames vistos na janela atual para detectar
        # frame congelado (pipeline travado entregando o mesmo buffer N
        # vezes para a inferência) — sintoma clássico de aliasing ou de
        # captura travada.
        self._unique_frame_hashes_window = 0
        self._last_frame_hash_window: Optional[int] = None
        self._last_frame_hash_overall: Optional[int] = None
        # Dump da primeira inferência (independente de WARNING) para que o
        # operador veja exatamente o que a câmera está entregando ao modelo
        # quando o sistema "começa a operar". Diagnóstico mais útil em
        # campo do que ler logs estruturados.
        self._first_frame_dumped = False
        # Quantos frames iniciais imprimimos stats por-frame em INFO; após
        # isso voltamos ao log periódico agregado para não poluir o log.
        self._verbose_first_frames = 5
    
    def set_frame(self, frame: np.ndarray, frame_id: int) -> None:
        """Define o frame para inferência."""
        self._mutex.lock()
        self._current_frame = frame
        self._frame_id = frame_id
        self._frame_condition.wakeAll()
        self._mutex.unlock()
    
    def run(self) -> None:
        """Loop principal de inferência."""
        self._running = True
        frame_interval = 1.0 / self._target_fps if self._target_fps > 0 else 0.066
        
        logger.info("inference_worker_started", target_fps=self._target_fps)
        
        while self._running:
            # Verifica pause
            self._mutex.lock()
            while self._paused and self._running:
                self._pause_condition.wait(self._mutex)
            
            # Aguarda frame
            if self._current_frame is None and self._running:
                self._frame_condition.wait(self._mutex, int(frame_interval * 1000))
            
            frame = self._current_frame
            frame_id = self._frame_id
            self._current_frame = None
            self._mutex.unlock()
            
            if not self._running or frame is None:
                continue
            
            start_time = time.perf_counter()
            
            try:
                self._maybe_dump_first_frame(frame, frame_id)
                result = self._run_inference(frame, frame_id)

                if result is not None:
                    self._update_diagnostic_stats(result, frame)
                    self._maybe_log_per_frame(result, frame, frame_id)
                    self.detection_ready.emit(result)

            except Exception as e:
                logger.error("inference_error", error=str(e))
                self.error_occurred.emit(str(e))
            
            # Controle de FPS
            elapsed = time.perf_counter() - start_time
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        # Log final agregado para garantir que não haja "fim silencioso"
        # de uma sessão sem detecções.
        self._emit_diagnostic_log(force=True)
        logger.info("inference_worker_stopped")

    def _update_diagnostic_stats(
        self,
        result: DetectionResult,
        frame: Optional[np.ndarray] = None,
    ) -> None:
        """Acumula estatísticas e emite log periódico de diagnóstico."""
        self._frames_processed += 1
        self._sum_inference_ms += float(result.inference_time_ms or 0.0)
        if result.has_detections:
            self._frames_with_detection += 1
        if result.raw_segment_count > 0:
            self._frames_with_segments_above_threshold += 1
        if result.rejected_by_class > 0:
            self._frames_rejected_by_class += 1
        if result.max_query_score is not None:
            if result.max_query_score > self._max_query_score_seen:
                self._max_query_score_seen = float(result.max_query_score)

        if frame is not None and frame.size > 0:
            try:
                fmean = float(frame.mean())
                fstd = float(frame.std())
                self._sum_frame_mean += fmean
                self._sum_frame_std += fstd
                self._frame_stat_count += 1
                if fmean < self._min_frame_mean:
                    self._min_frame_mean = fmean
                if fmean > self._max_frame_mean:
                    self._max_frame_mean = fmean
                # Cache barato para um eventual dump diagnóstico (apenas referência).
                self._last_sample_frame = frame
                # Hash CRC32 sobre uma amostra do buffer para detectar frame
                # congelado/duplicado entre captura e inferência. Usar a
                # imagem inteira é caro (640x480x3 = 921KB); amostramos para
                # manter custo desprezível e mesmo assim detectar mudanças.
                fhash = self._compute_frame_hash(frame)
                if fhash != self._last_frame_hash_window:
                    self._unique_frame_hashes_window += 1
                    self._last_frame_hash_window = fhash
                self._last_frame_hash_overall = fhash
            except Exception:
                pass

        if (self._frames_processed - self._last_diagnostic_log_frame) >= self._diagnostic_log_interval:
            self._emit_diagnostic_log(force=False)

    @staticmethod
    def _compute_frame_hash(frame: np.ndarray) -> int:
        """
        Hash leve de um frame (uint8 BGR) suficiente para detectar mudanças.
        Não é criptográfico — só serve como assinatura para o operador
        verificar se o pipeline está entregando frames novos. Amostra a
        cada 16ª linha para custar O(H/16 * W * C) ao invés de O(H*W*C).
        """
        try:
            sample = frame[::16, :, :] if frame.ndim == 3 else frame[::16, :]
            return int(np.uint32(hash(sample.tobytes())) & 0xFFFFFFFF)
        except Exception:
            return 0

    def _maybe_dump_first_frame(self, frame: np.ndarray, frame_id: int) -> None:
        """
        Salva no disco o PRIMEIRO frame que chega à inferência (apenas uma
        vez por sessão). Isso é independente de qualquer WARNING e serve
        como evidência visual direta de "o que a câmera está entregando
        ao modelo quando o app começa a operar". Em campo, é a forma mais
        rápida de detectar:
          - Câmera errada selecionada (continuity camera reordenou índice)
          - Lente coberta/embalagem fora do FOV
          - Iluminação/exposição quebradas
          - Aliasing de buffer entregando lixo
        """
        if self._first_frame_dumped:
            return
        if self._diagnostic_dump_dir is None:
            return
        if frame is None or frame.size == 0:
            return
        try:
            import cv2

            self._diagnostic_dump_dir.mkdir(parents=True, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            out_path = self._diagnostic_dump_dir / f"first_inference_frame_{ts}.png"
            cv2.imwrite(str(out_path), frame)
            self._first_frame_dumped = True
            logger.info(
                "first_inference_frame_dumped",
                path=str(out_path),
                frame_id=frame_id,
                shape=list(frame.shape),
                mean=round(float(frame.mean()), 2),
                std=round(float(frame.std()), 2),
                hint=(
                    "abra esta imagem para conferir se a câmera está "
                    "entregando o que você esperava (FOV, exposição, etc.)"
                ),
            )
        except Exception as exc:
            logger.warning("first_inference_frame_dump_failed", error=str(exc))

    def _maybe_log_per_frame(
        self,
        result: DetectionResult,
        frame: Optional[np.ndarray],
        frame_id: int,
    ) -> None:
        """
        Emite log INFO detalhado nos primeiros N frames da sessão, com
        estatísticas do frame e o max_query_score do modelo. Permite ao
        operador ver imediatamente o que a inferência está vendo, sem
        precisar esperar o log periódico (`inference_diagnostic`).
        """
        if self._frames_processed > self._verbose_first_frames:
            return
        if frame is None or frame.size == 0:
            logger.info(
                "inference_first_frames",
                seq=self._frames_processed,
                frame_id=frame_id,
                detections=result.count,
                max_query_score=(
                    round(float(result.max_query_score), 4)
                    if result.max_query_score is not None else None
                ),
                inference_ms=round(float(result.inference_time_ms or 0.0), 2),
            )
            return
        logger.info(
            "inference_first_frames",
            seq=self._frames_processed,
            frame_id=frame_id,
            detections=result.count,
            max_query_score=(
                round(float(result.max_query_score), 4)
                if result.max_query_score is not None else None
            ),
            frame_mean=round(float(frame.mean()), 2),
            frame_std=round(float(frame.std()), 2),
            frame_min=int(frame.min()),
            frame_max=int(frame.max()),
            frame_hash=self._last_frame_hash_overall,
            inference_ms=round(float(result.inference_time_ms or 0.0), 2),
        )

    def _emit_diagnostic_log(self, force: bool) -> None:
        """Emite log INFO agregado e zera a janela de medição."""
        if self._frames_processed == 0:
            return
        if not force and self._frames_processed == self._last_diagnostic_log_frame:
            return
        window = self._frames_processed - self._last_diagnostic_log_frame
        avg_ms = self._sum_inference_ms / max(1, window)
        has_frame_stats = self._frame_stat_count > 0
        avg_frame_mean = (
            self._sum_frame_mean / self._frame_stat_count
            if has_frame_stats else None
        )
        avg_frame_std = (
            self._sum_frame_std / self._frame_stat_count
            if has_frame_stats else None
        )
        threshold = getattr(self._postprocessor, "confidence_threshold", None)

        # Heurística: identifica situações em que o modelo silenciosamente "não vê" nada.
        no_detections = self._frames_with_detection == 0
        suspicious_threshold = (
            no_detections
            and threshold is not None
            and 0.0 < self._max_query_score_seen < float(threshold)
        )
        # Frame "preto"/uniforme = câmera sem imagem útil (lente coberta, sem
        # auto-exposição, formato errado). std<5 em uint8 indica imagem quase
        # constante; mean<5 indica frame totalmente escuro. Só avaliamos
        # quando temos estatísticas reais do frame (em testes podem faltar).
        suspicious_frame = (
            no_detections
            and has_frame_stats
            and (avg_frame_mean < 5.0 or avg_frame_std < 5.0)
        )
        # max_query_score próximo de zero = modelo confiante de que NÃO há embalagem.
        # Pode ser cena vazia, oclusão, foco/exposição ruim, ou modelo fora do domínio.
        suspicious_zero_score = (
            no_detections
            and 0.0 < self._max_query_score_seen < 0.05
        )

        # Frames "congelados": pipeline entregou poucos hashes únicos quando
        # comparado ao número de frames processados. Sintoma típico de
        # aliasing de buffer ou de captura travada (a câmera/USB está enviando
        # o mesmo conteúdo repetidamente para a inferência).
        suspicious_frozen = (
            no_detections
            and has_frame_stats
            and window >= 5
            and self._unique_frame_hashes_window <= max(1, window // 5)
        )

        suspicious = (
            suspicious_threshold
            or suspicious_frame
            or suspicious_zero_score
            or suspicious_frozen
        )
        hint = None
        # Ordem de prioridade do hint (mais específico primeiro):
        # 1) pipeline entregando o mesmo frame (frozen) — bug de captura/aliasing
        # 2) frame inválido (câmera fundamental quebrada)
        # 3) score ~0 (modelo confiante de que não há embalagem) — geralmente
        #    indica FOV vazio ou modelo fora de domínio, NÃO threshold mal calibrado
        # 4) score abaixo do threshold (threshold só) — calibração de operação
        if suspicious_frozen:
            hint = (
                "pipeline entregando o mesmo frame repetido à inferência "
                "(bug de captura/aliasing? câmera travada?). Verifique se o "
                "stream está rodando e se o índice da câmera é o correto."
            )
        elif suspicious_frame:
            hint = (
                "frame parece preto ou sem variação (lente coberta? câmera USB sem "
                "imagem? formato errado?). Verifique a janela de Operação."
            )
        elif suspicious_zero_score:
            hint = (
                "modelo confiante de que NÃO há embalagem no frame. Verifique "
                "se a embalagem está no FOV, com foco e iluminação adequados; "
                "ou se o modelo carregado é o correto para este produto."
            )
        elif suspicious_threshold:
            hint = (
                "max_query_score abaixo do threshold; considere reduzir "
                "detection.confidence_threshold ou checar iluminação/ROI"
            )

        log_fn = logger.warning if suspicious else logger.info
        log_fn(
            "inference_diagnostic",
            frames=window,
            detections=self._frames_with_detection,
            raw_segments_frames=self._frames_with_segments_above_threshold,
            rejected_by_class_frames=self._frames_rejected_by_class,
            avg_inference_ms=round(avg_ms, 2),
            max_query_score=round(self._max_query_score_seen, 4),
            confidence_threshold=threshold,
            avg_frame_mean=(round(avg_frame_mean, 2) if has_frame_stats else None),
            avg_frame_std=(round(avg_frame_std, 2) if has_frame_stats else None),
            min_frame_mean=(
                round(self._min_frame_mean, 2)
                if self._min_frame_mean != float("inf") else None
            ),
            max_frame_mean=(
                round(self._max_frame_mean, 2) if has_frame_stats else None
            ),
            unique_frame_hashes=self._unique_frame_hashes_window,
            last_frame_hash=self._last_frame_hash_overall,
            hint=hint,
        )

        # Em caso de WARNING, salva uma amostra do último frame para inspeção visual
        # (apenas uma vez por sessão, para não encher o disco).
        if (
            suspicious
            and self._diagnostic_dump_dir is not None
            and not self._dumped_diagnostic_sample
            and self._last_sample_frame is not None
        ):
            try:
                import cv2

                self._diagnostic_dump_dir.mkdir(parents=True, exist_ok=True)
                ts = time.strftime("%Y%m%d_%H%M%S")
                out_path = self._diagnostic_dump_dir / f"diagnostic_sample_{ts}.png"
                cv2.imwrite(str(out_path), self._last_sample_frame)
                logger.warning(
                    "diagnostic_sample_dumped",
                    path=str(out_path),
                    hint=(
                        "abra esta imagem para verificar visualmente o que a câmera "
                        "está enviando ao modelo no momento do diagnóstico"
                    ),
                )
                self._dumped_diagnostic_sample = True
            except Exception as exc:
                logger.warning("diagnostic_sample_dump_failed", error=str(exc))

        self._last_diagnostic_log_frame = self._frames_processed
        self._frames_with_detection = 0
        self._frames_with_segments_above_threshold = 0
        self._frames_rejected_by_class = 0
        self._sum_inference_ms = 0.0
        self._max_query_score_seen = 0.0
        self._sum_frame_mean = 0.0
        self._sum_frame_std = 0.0
        self._frame_stat_count = 0
        self._min_frame_mean = float("inf")
        self._max_frame_mean = 0.0
        self._unique_frame_hashes_window = 0
        self._last_frame_hash_window = None
    
    def _run_inference(self, frame: np.ndarray, frame_id: int) -> Optional[DetectionResult]:
        """Executa inferência em um frame."""
        start_time = time.perf_counter()
        
        # Converte BGR para RGB
        rgb_frame = frame[:, :, ::-1]
        
        # Converte para PIL Image
        pil_image = Image.fromarray(rgb_frame)
        
        # Processa imagem
        inputs = self._processor(images=pil_image, return_tensors="pt")
        inputs = {k: v.to(self._device) for k, v in inputs.items()}
        
        # Inferência
        with torch.no_grad():
            outputs = self._model(**inputs)

        # Pós-processamento é mais estável em CPU (especialmente MPS com interpolate
        # de máscaras no Mask2Former). Move outputs para CPU antes do post-process.
        if self._device != "cpu":
            outputs = self._move_outputs_to_cpu(outputs)

        target_sizes = torch.tensor([[frame.shape[0], frame.shape[1]]], device="cpu")

        inference_time = (time.perf_counter() - start_time) * 1000

        result = self._postprocessor.process(
            outputs=outputs,
            target_sizes=target_sizes,
            id2label=self._model.config.id2label,
            frame_id=frame_id,
            inference_time_ms=inference_time,
        )

        return result

    @staticmethod
    def _move_outputs_to_cpu(outputs: Any) -> Any:
        """Move todos os tensores de um output de modelo para CPU (in-place nos campos)."""
        if outputs is None:
            return outputs
        try:
            for key in outputs.keys():
                value = outputs.get(key)
                if isinstance(value, torch.Tensor):
                    outputs[key] = value.detach().to("cpu")
                elif isinstance(value, (list, tuple)) and value and isinstance(value[0], torch.Tensor):
                    outputs[key] = type(value)(v.detach().to("cpu") for v in value)
        except Exception:
            pass
        return outputs
    
    def pause(self) -> None:
        """Pausa a inferência."""
        self._mutex.lock()
        self._paused = True
        self._mutex.unlock()
    
    def resume(self) -> None:
        """Retoma a inferência."""
        self._mutex.lock()
        self._paused = False
        self._pause_condition.wakeAll()
        self._mutex.unlock()
    
    def stop(self) -> None:
        """Para a inferência."""
        self._running = False
        self._mutex.lock()
        self._paused = False
        self._pause_condition.wakeAll()
        self._frame_condition.wakeAll()
        self._mutex.unlock()
        self.wait()


class InferenceEngine(QObject):
    """
    Engine principal de inferência.
    
    Singleton que gerencia:
    - Carregamento de modelo
    - Thread de inferência
    - Pós-processamento
    
    Signals:
        detection_event: Emitido quando uma detecção ocorre
        detection_result: Emitido com resultado completo
        inference_started: Emitido quando inferência inicia
        inference_stopped: Emitido quando inferência para
        model_loaded: Emitido quando modelo é carregado
    """
    
    detection_event = Signal(object)  # DetectionEvent
    detection_result = Signal(object)  # DetectionResult
    inference_started = Signal()
    inference_stopped = Signal()
    model_loaded = Signal(str)
    
    _instance: Optional["InferenceEngine"] = None
    _lock = Lock()
    
    def __new__(cls) -> "InferenceEngine":
        """Singleton pattern."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        
        super().__init__()
        self._initialized = True
        
        self._settings = get_settings()
        self._loader = ModelLoader()
        # Pós-processador é escolhido após carregar o modelo (ver _build_postprocessor).
        # Inicia com um pós-processador para object detection como fallback seguro.
        self._postprocessor: Any = PostProcessor(
            confidence_threshold=self._settings.detection.confidence_threshold,
            max_detections=self._settings.detection.max_detections,
            target_classes=self._settings.detection.target_classes,
        )
        self._metrics = MetricsCollector()
        
        self._worker: Optional[InferenceWorker] = None
        self._is_running = False
        self._last_result: Optional[DetectionResult] = None
    
    def load_model(self, model_path: str = None, device: str = None) -> bool:
        """
        Carrega o modelo.
        
        Args:
            model_path: Caminho ou ID do modelo
            device: Device (cpu, cuda, auto)
        
        Returns:
            True se carregado com sucesso
        """
        if model_path is None:
            # 1) Respeita explicitamente o caminho definido na config
            cfg_path = (self._settings.detection.model_path or "").strip()
            if cfg_path:
                resolved = self._resolve_model_path(cfg_path)
                if resolved is not None and self._has_local_model(resolved):
                    model_path = str(resolved)
                    logger.info("using_configured_model", path=model_path)
                else:
                    # Config aponta para um ID do Hugging Face ou caminho não-local válido
                    model_path = cfg_path
                    logger.info("using_configured_model_as_id", model=model_path)
            else:
                # 2) Fallback final: modelo padrão do Hugging Face
                model_path = self._settings.detection.default_model
                logger.info("using_huggingface_model", model=model_path)
        
        if device is None:
            device = self._settings.detection.device
        
        try:
            self._loader.load(model_path, device)
            # Reconfigura o pós-processador com base na task detectada.
            self._postprocessor = self._build_postprocessor()
            logger.info(
                "model_loaded",
                model=model_path,
                device=self._loader.device,
                task=self._loader.task,
            )
            self.model_loaded.emit(model_path)
            return True
        except Exception as e:
            logger.error("model_load_failed", error=str(e))
            return False

    def _build_postprocessor(self) -> Any:
        """Cria o pós-processador apropriado à task do modelo carregado."""
        detection = self._settings.detection
        if self._loader.task == TASK_INSTANCE_SEGMENTATION:
            logger.info("using_segmentation_postprocessor")
            return SegmentationPostProcessor(
                processor=self._loader.processor,
                confidence_threshold=detection.confidence_threshold,
                max_detections=detection.max_detections,
                target_classes=detection.target_classes,
                min_mask_pixels=getattr(detection, "segmentation_min_mask_pixels", 64),
                mask_threshold=getattr(detection, "segmentation_mask_threshold", 0.5),
                overlap_mask_area_threshold=getattr(
                    detection,
                    "segmentation_overlap_mask_area_threshold",
                    0.8,
                ),
            )
        logger.info("using_object_detection_postprocessor")
        return PostProcessor(
            confidence_threshold=detection.confidence_threshold,
            max_detections=detection.max_detections,
            target_classes=detection.target_classes,
        )
    
    def _resolve_model_path(self, model_path: str) -> Optional[Path]:
        """
        Resolve `model_path` (absoluto ou relativo ao root do projeto) para um Path.
        Retorna None se o caminho não existir como diretório.
        """
        p = Path(model_path)
        if not p.is_absolute():
            base = Path(__file__).parent.parent
            p = base / p
        if p.exists() and p.is_dir():
            return p
        return None
    
    def _has_local_model(self, models_dir: Path) -> bool:
        """
        Verifica se existe um modelo local válido no diretório.
        
        Args:
            models_dir: Diretório de modelos
        
        Returns:
            True se modelo local existe e é válido
        """
        required_files = [
            "config.json",
            "preprocessor_config.json",
        ]
        
        # Verifica se existe pelo menos um arquivo de pesos
        weight_files = [
            "model.safetensors",
            "pytorch_model.bin",
            "model.bin",
        ]
        
        # Verifica arquivos obrigatórios
        for file in required_files:
            if not (models_dir / file).exists():
                return False
        
        # Verifica se existe pelo menos um arquivo de pesos
        has_weights = any((models_dir / weight).exists() for weight in weight_files)
        
        return has_weights
    
    def start(self) -> bool:
        """
        Inicia a inferência.
        
        Returns:
            True se iniciado com sucesso
        """
        if self._is_running:
            logger.warning("inference_already_running")
            return True
        
        if not self._loader.is_loaded:
            logger.error("model_not_loaded")
            return False
        
        try:
            # Diretório de dump diagnóstico: ./logs/diagnostic_samples/
            # (relativo ao cwd no momento da execução do app).
            dump_dir = Path("logs") / "diagnostic_samples"

            self._worker = InferenceWorker(
                model=self._loader.model,
                processor=self._loader.processor,
                postprocessor=self._postprocessor,
                device=self._loader.device,
                target_fps=self._settings.detection.inference_fps,
                diagnostic_dump_dir=str(dump_dir),
            )
            self._worker.detection_ready.connect(self._on_detection_ready)
            self._worker.error_occurred.connect(self._on_error)
            
            # Inicia
            self._worker.start()
            self._is_running = True
            
            logger.info("inference_started", fps=self._settings.detection.inference_fps)
            self.inference_started.emit()
            return True
            
        except Exception as e:
            logger.error("inference_start_failed", error=str(e))
            return False
    
    def stop(self) -> None:
        """Para a inferência."""
        if not self._is_running:
            return
        
        if self._worker is not None:
            self._worker.stop()
            if self._worker.isRunning():
                self._worker.wait(5000)
            self._worker.deleteLater()
            self._worker = None
        
        self._is_running = False
        logger.info("inference_stopped")
        self.inference_stopped.emit()
    
    def pause(self) -> None:
        """Pausa a inferência."""
        if self._worker is not None:
            self._worker.pause()
            logger.info("inference_paused")
    
    def resume(self) -> None:
        """Retoma a inferência."""
        if self._worker is not None:
            self._worker.resume()
            logger.info("inference_resumed")
    
    def process_frame(self, frame: np.ndarray, frame_id: int = 0) -> None:
        """
        Envia um frame para processamento.
        
        Args:
            frame: Frame BGR
            frame_id: ID do frame
        """
        if self._worker is not None and self._is_running:
            self._worker.set_frame(frame, frame_id)
    
    def set_confidence_threshold(self, threshold: float) -> None:
        """Define threshold de confiança."""
        self._postprocessor.set_confidence_threshold(threshold)
        self._settings.detection.confidence_threshold = threshold
    
    def set_max_detections(self, max_detections: int) -> None:
        """Define máximo de detecções."""
        self._postprocessor.set_max_detections(max_detections)
        self._settings.detection.max_detections = max_detections
    
    def set_target_classes(self, classes: Optional[List[str]]) -> None:
        """Define classes alvo."""
        self._postprocessor.set_target_classes(classes)
        self._settings.detection.target_classes = classes
    
    def get_status(self) -> Dict[str, Any]:
        """Retorna status da engine."""
        return {
            "running": self._is_running,
            "model_loaded": self._loader.is_loaded,
            "model_info": self._loader.get_model_info(),
            "device": self._loader.device,
            "confidence_threshold": self._postprocessor.confidence_threshold,
            "max_detections": self._postprocessor.max_detections,
            "last_detection_count": self._last_result.count if self._last_result else 0,
        }
    
    @property
    def is_running(self) -> bool:
        """Verifica se está rodando."""
        return self._is_running
    
    @property
    def is_model_loaded(self) -> bool:
        """Verifica se modelo está carregado."""
        return self._loader.is_loaded
    
    @property
    def last_result(self) -> Optional[DetectionResult]:
        """Retorna último resultado."""
        return self._last_result
    
    def _on_detection_ready(self, result: DetectionResult) -> None:
        """Handler para detecção pronta."""
        self._last_result = result
        
        # Métricas
        self._metrics.record("inference_time", result.inference_time_ms)
        self._metrics.record("detection_count", result.count)
        if result.has_detections:
            best = result.best_detection
            self._metrics.record("detection_confidence", best.confidence * 100)
        
        # Cria evento
        event = DetectionEvent.from_result(result)
        
        # Emite sinais
        self.detection_result.emit(result)
        self.detection_event.emit(event)
        
        if result.has_detections:
            logger.debug(
                "detection_found",
                count=result.count,
                best_class=result.best_detection.class_name,
                best_confidence=result.best_detection.confidence,
                inference_time=result.inference_time_ms,
            )
    
    def _on_error(self, error: str) -> None:
        """Handler para erro."""
        logger.error("inference_worker_error", error=error)


# Função de conveniência
def get_inference_engine() -> InferenceEngine:
    """Retorna a instância da engine de inferência."""
    return InferenceEngine()
