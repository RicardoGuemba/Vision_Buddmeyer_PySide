# -*- coding: utf-8 -*-
"""
Carregador de modelos de detecção.

Suporta:
- Object detection clássico (DETR/RT-DETR) via `AutoModelForObjectDetection`.
- Instance segmentation (Mask2Former) via `Mask2FormerForUniversalSegmentation`.

Determina o tipo de modelo lendo `config.json` (campo `model_type` e
`architectures`) e escolhe a classe correta do transformers. Expõe a
propriedade `task` para o `InferenceEngine` selecionar o pós-processador
adequado.
"""

import json
import warnings
from pathlib import Path
from typing import Optional, Tuple, Any, Dict
import torch

from core.logger import get_logger
from core.exceptions import ModelLoadError

logger = get_logger("detection.loader")


# Tasks suportadas pelo pipeline
TASK_OBJECT_DETECTION = "object_detection"
TASK_INSTANCE_SEGMENTATION = "instance_segmentation"


class ModelLoader:
    """
    Carregador de modelos de visão do Hugging Face.

    Suporta modelos locais e download do hub. Identifica automaticamente
    modelos de instance segmentation (ex.: Mask2Former) e carrega com a
    classe correta do transformers.
    """
    
    # Modelos padrão suportados (IDs do hub)
    SUPPORTED_MODELS = {
        "rtdetr_r50vd": "PekingU/rtdetr_r50vd",
        "rtdetr_r101vd": "PekingU/rtdetr_r101vd",
        "detr_resnet50": "facebook/detr-resnet-50",
        "detr_resnet101": "facebook/detr-resnet-101",
        "mask2former_swin_tiny_coco": "facebook/mask2former-swin-tiny-coco-instance",
    }

    # Tipos de modelo (config.json -> model_type) que são instance segmentation
    _SEGMENTATION_MODEL_TYPES = {
        "mask2former",
        "maskformer",
        "oneformer",
    }

    def __init__(self):
        self._model = None
        self._processor = None
        self._device: str = "cpu"
        self._model_name: str = ""
        self._task: str = TASK_OBJECT_DETECTION
    
    def load(
        self,
        model_path: str,
        device: str = "auto",
    ) -> Tuple[Any, Any]:
        """
        Carrega modelo e processador.
        
        Args:
            model_path: Caminho local ou ID do Hugging Face
            device: Device (cpu, cuda, auto)
        
        Returns:
            Tuple (model, processor)
        """
        try:
            from transformers import (
                AutoModelForObjectDetection,
                AutoImageProcessor,
            )
        except ImportError:
            raise ModelLoadError(
                "Transformers não instalado. Execute: pip install transformers",
                {"package": "transformers"}
            )

        # Determina device
        self._device = self._resolve_device(device)
        logger.info("loading_model", model_path=model_path, device=self._device)
        
        try:
            # Verifica se é caminho local
            local_path = Path(model_path)
            
            # Se for caminho relativo, tenta resolver
            if not local_path.is_absolute():
                # Tenta resolver em relação ao diretório do projeto
                base_path = Path(__file__).parent.parent
                local_path = base_path / model_path
            
            if local_path.exists() and local_path.is_dir():
                # Verifica se tem arquivos de modelo válidos
                has_config = (local_path / "config.json").exists()
                has_preprocessor = (local_path / "preprocessor_config.json").exists()
                has_weights = any(
                    (local_path / weight).exists()
                    for weight in ["model.safetensors", "pytorch_model.bin", "model.bin"]
                )
                
                if has_config and has_preprocessor and has_weights:
                    model_source = str(local_path)
                    logger.info("loading_local_model", path=model_source)
                else:
                    # Diretório existe mas não tem modelo válido, usa Hugging Face
                    logger.warning("local_path_invalid_using_hf", path=str(local_path))
                    model_source = model_path
                    logger.info("loading_hf_model", model_id=model_source)
            else:
                # Usa como ID do Hugging Face
                model_source = model_path
                logger.info("loading_hf_model", model_id=model_source)
            
            # Detecta a "task" (object_detection vs instance_segmentation)
            # lendo o config.json antes de instanciar o modelo. Isto evita
            # trocar erros silenciosos no post-processing por erros cedo.
            self._task = self._detect_task(model_source)

            # Suprime UserWarnings durante o carregamento (PyTorch/timm "assign=True", etc.)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)

                # Processor: Mask2Former usa Mask2FormerImageProcessor,
                # modelos DETR usam processors específicos. AutoImageProcessor
                # resolve automaticamente para ambos quando a config existe.
                # use_fast=True não é suportado para Mask2Former (fallback silencioso).
                try:
                    self._processor = AutoImageProcessor.from_pretrained(
                        model_source,
                        use_fast=True,
                    )
                except (TypeError, ValueError):
                    self._processor = AutoImageProcessor.from_pretrained(model_source)

                # Modelo: seleciona classe correta pela task detectada.
                if self._task == TASK_INSTANCE_SEGMENTATION:
                    try:
                        from transformers import Mask2FormerForUniversalSegmentation
                    except ImportError:
                        raise ModelLoadError(
                            "Transformers sem suporte a Mask2Former. Atualize: pip install -U transformers",
                            {"package": "transformers"},
                        )
                    self._model = Mask2FormerForUniversalSegmentation.from_pretrained(
                        model_source,
                    )
                else:
                    self._model = AutoModelForObjectDetection.from_pretrained(
                        model_source,
                    )

            self._model.to(self._device)
            self._model.eval()

            self._model_name = model_path

            logger.info(
                "model_loaded",
                model=model_path,
                device=self._device,
                task=self._task,
                num_labels=getattr(self._model.config, "num_labels", None),
            )

            return self._model, self._processor
            
        except Exception as e:
            logger.error("model_load_failed", error=str(e), model_path=model_path)
            raise ModelLoadError(
                f"Falha ao carregar modelo: {e}",
                {"model_path": model_path, "error": str(e)}
            )
    
    def _detect_task(self, model_source: str) -> str:
        """
        Inspeciona config.json e task.json (se existir) para determinar a
        task do modelo.

        Regras (ordem de prioridade):
          1. task.json -> campo `task`
          2. config.json -> `model_type` pertence a _SEGMENTATION_MODEL_TYPES
          3. config.json -> `architectures` contém "*Segmentation*"
          4. Fallback: object_detection
        """
        try:
            src_path = Path(model_source)
            if src_path.exists() and src_path.is_dir():
                task_file = src_path / "task.json"
                if task_file.exists():
                    try:
                        with open(task_file, "r", encoding="utf-8") as f:
                            task_data = json.load(f)
                        task_value = str(task_data.get("task", "")).strip().lower()
                        if task_value == "instance_segmentation":
                            return TASK_INSTANCE_SEGMENTATION
                        if task_value == "object_detection":
                            return TASK_OBJECT_DETECTION
                    except Exception as e:
                        logger.warning("task_json_parse_failed", error=str(e))

                config_file = src_path / "config.json"
                if config_file.exists():
                    try:
                        with open(config_file, "r", encoding="utf-8") as f:
                            cfg = json.load(f)
                    except Exception as e:
                        logger.warning("config_json_parse_failed", error=str(e))
                        cfg = {}

                    model_type = str(cfg.get("model_type", "")).strip().lower()
                    if model_type in self._SEGMENTATION_MODEL_TYPES:
                        return TASK_INSTANCE_SEGMENTATION

                    archs = cfg.get("architectures") or []
                    if any("segmentation" in str(a).lower() for a in archs):
                        return TASK_INSTANCE_SEGMENTATION

            # Heurística para modelos do hub (sem path local): por nome
            name_lower = str(model_source).lower()
            if any(
                keyword in name_lower
                for keyword in ("mask2former", "maskformer", "oneformer", "segmentation")
            ):
                return TASK_INSTANCE_SEGMENTATION
        except Exception as e:
            logger.warning("task_detection_failed", error=str(e))

        return TASK_OBJECT_DETECTION

    def _resolve_device(self, device: str) -> str:
        """
        Resolve o device a ser usado.
        
        Args:
            device: cpu, cuda, mps (Apple Silicon), ou auto
        
        Returns:
            Device resolvido
        """
        if device == "auto":
            if torch.cuda.is_available():
                return "cuda"
            if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
                logger.info("using_mps_apple_silicon")
                return "mps"
            logger.info("cuda_not_available_using_cpu")
            return "cpu"
        if device == "cuda":
            if not torch.cuda.is_available():
                logger.warning("cuda_not_available_fallback_cpu")
                return "cpu"
            return "cuda"
        if device == "mps":
            if not (getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()):
                logger.warning("mps_not_available_fallback_cpu")
                return "cpu"
            return "mps"
        return "cpu"
    
    @property
    def model(self) -> Any:
        """Retorna o modelo carregado."""
        return self._model
    
    @property
    def processor(self) -> Any:
        """Retorna o processador carregado."""
        return self._processor
    
    @property
    def device(self) -> str:
        """Retorna o device atual."""
        return self._device
    
    @property
    def model_name(self) -> str:
        """Retorna o nome do modelo."""
        return self._model_name

    @property
    def task(self) -> str:
        """Retorna a task do modelo atual (object_detection|instance_segmentation)."""
        return self._task
    
    @property
    def is_loaded(self) -> bool:
        """Verifica se modelo está carregado."""
        return self._model is not None and self._processor is not None
    
    def get_model_info(self) -> Dict[str, Any]:
        """Retorna informações do modelo."""
        if not self.is_loaded:
            return {"loaded": False}
        
        return {
            "loaded": True,
            "name": self._model_name,
            "device": self._device,
            "task": self._task,
            "num_labels": getattr(self._model.config, "num_labels", None),
            "id2label": getattr(self._model.config, "id2label", {}),
        }
    
    def unload(self) -> None:
        """Descarrega o modelo."""
        if self._model is not None:
            del self._model
            self._model = None
        
        if self._processor is not None:
            del self._processor
            self._processor = None
        
        # Limpa cache de GPU
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        logger.info("model_unloaded")
    
    @staticmethod
    def get_cuda_info() -> Dict[str, Any]:
        """Retorna informações sobre CUDA."""
        if not torch.cuda.is_available():
            return {"available": False}
        
        return {
            "available": True,
            "device_count": torch.cuda.device_count(),
            "current_device": torch.cuda.current_device(),
            "device_name": torch.cuda.get_device_name(0),
            "memory_allocated": torch.cuda.memory_allocated(0),
            "memory_reserved": torch.cuda.memory_reserved(0),
        }
