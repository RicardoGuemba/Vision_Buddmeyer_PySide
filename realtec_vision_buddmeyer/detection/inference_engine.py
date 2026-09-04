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
    ):
        super().__init__()
        
        self._model = model
        self._processor = processor
        self._postprocessor = postprocessor
        self._device = device
        self._target_fps = target_fps
        
        self._running = False
        self._paused = False
        self._current_frame: Optional[np.ndarray] = None
        self._frame_id = 0
        
        self._mutex = QMutex()
        self._pause_condition = QWaitCondition()
        self._frame_condition = QWaitCondition()
    
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
                result = self._run_inference(frame, frame_id)
                
                if result is not None:
                    self.detection_ready.emit(result)
                    
            except Exception as e:
                logger.error("inference_error", error=str(e))
                self.error_occurred.emit(str(e))
            
            # Controle de FPS
            elapsed = time.perf_counter() - start_time
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
        
        logger.info("inference_worker_stopped")
    
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
        if not self.wait(8000):
            logger.warning("inference_worker_stop_timeout")


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
            # Cria worker
            self._worker = InferenceWorker(
                model=self._loader.model,
                processor=self._loader.processor,
                postprocessor=self._postprocessor,
                device=self._loader.device,
                target_fps=self._settings.detection.inference_fps,
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
