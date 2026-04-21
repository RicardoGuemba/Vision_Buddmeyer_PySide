# -*- coding: utf-8 -*-
"""
Validador de modelos locais.
Verifica se todos os arquivos necessários estão presentes.
"""

from pathlib import Path
from typing import List, Dict, Tuple
import json

from core.logger import get_logger

logger = get_logger("detection.validator")


class ModelValidator:
    """
    Validador de modelos de visão locais.

    Suporta tanto object detection (DETR/RT-DETR) quanto instance
    segmentation (Mask2Former/MaskFormer/OneFormer).
    """

    # Tipos de modelo aceitos no config.json (model_type)
    ACCEPTED_MODEL_TYPES = (
        "detr",
        "rtdetr",
        "rt_detr",
        "conditional_detr",
        "deformable_detr",
        "mask2former",
        "maskformer",
        "oneformer",
    )

    # Arquivos obrigatórios
    REQUIRED_FILES = [
        "config.json",
        "preprocessor_config.json",
    ]
    
    # Arquivos de pesos (pelo menos um deve existir)
    WEIGHT_FILES = [
        "model.safetensors",  # Formato preferido (seguro)
        "pytorch_model.bin",  # Formato alternativo
        "model.bin",          # Formato alternativo
    ]
    
    # Arquivos opcionais
    OPTIONAL_FILES = [
        "class_config.json",  # Configuração de classes customizada
        "README.md",          # Documentação
        "tokenizer_config.json",  # Configuração de tokenizer (se aplicável)
    ]
    
    @classmethod
    def validate_model_directory(cls, models_dir: Path) -> Tuple[bool, List[str], List[str]]:
        """
        Valida um diretório de modelo.
        
        Args:
            models_dir: Caminho do diretório de modelos
        
        Returns:
            Tuple (is_valid, missing_files, warnings)
        """
        missing_files = []
        warnings = []
        
        if not models_dir.exists():
            return False, [f"Diretório não existe: {models_dir}"], []
        
        if not models_dir.is_dir():
            return False, [f"Não é um diretório: {models_dir}"], []
        
        # Verifica arquivos obrigatórios
        for file in cls.REQUIRED_FILES:
            file_path = models_dir / file
            if not file_path.exists():
                missing_files.append(file)
        
        # Verifica arquivos de pesos
        weight_found = False
        for weight_file in cls.WEIGHT_FILES:
            if (models_dir / weight_file).exists():
                weight_found = True
                break
        
        if not weight_found:
            missing_files.append("model.safetensors ou pytorch_model.bin")
        
        # Verifica arquivos opcionais
        for file in cls.OPTIONAL_FILES:
            if not (models_dir / file).exists():
                warnings.append(f"Arquivo opcional não encontrado: {file}")
        
        # Valida estrutura do config.json
        config_valid, config_errors = cls._validate_config_json(models_dir)
        if not config_valid:
            missing_files.extend(config_errors)
        
        is_valid = len(missing_files) == 0
        
        return is_valid, missing_files, warnings
    
    @classmethod
    def _validate_config_json(cls, models_dir: Path) -> Tuple[bool, List[str]]:
        """Valida o arquivo config.json."""
        config_file = models_dir / "config.json"
        
        if not config_file.exists():
            return False, ["config.json não encontrado"]
        
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
            
            # Verifica campos essenciais
            # num_labels pode não estar presente em alguns modelos, mas é recomendado
            required_fields = ["model_type"]
            recommended_fields = ["num_labels"]
            errors = []
            
            for field in required_fields:
                if field not in config:
                    errors.append(f"config.json: campo '{field}' ausente")
            
            # Avisa sobre campos recomendados
            for field in recommended_fields:
                if field not in config:
                    # Não é erro crítico, apenas aviso
                    pass
            
            # Verifica se é um modelo compatível (object detection ou segmentation)
            if "model_type" in config:
                model_type = str(config["model_type"]).lower()
                if not any(accepted in model_type for accepted in cls.ACCEPTED_MODEL_TYPES):
                    errors.append(
                        f"config.json: tipo de modelo '{model_type}' não está "
                        f"na lista de tipos suportados: {cls.ACCEPTED_MODEL_TYPES}"
                    )

            return len(errors) == 0, errors
            
        except json.JSONDecodeError as e:
            return False, [f"config.json: erro de parsing JSON: {e}"]
        except Exception as e:
            return False, [f"config.json: erro ao validar: {e}"]
    
    @classmethod
    def get_model_info(cls, models_dir: Path) -> Dict:
        """
        Obtém informações sobre o modelo.
        
        Args:
            models_dir: Diretório do modelo
        
        Returns:
            Dict com informações do modelo
        """
        info = {
            "path": str(models_dir),
            "exists": models_dir.exists(),
            "files": {},
            "config": None,
        }
        
        if not models_dir.exists():
            return info
        
        # Lista arquivos
        for file_path in models_dir.iterdir():
            if file_path.is_file():
                size = file_path.stat().st_size
                info["files"][file_path.name] = {
                    "size_bytes": size,
                    "size_mb": round(size / 1024 / 1024, 2),
                }
        
        # Carrega config.json se existir
        config_file = models_dir / "config.json"
        if config_file.exists():
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    info["config"] = json.load(f)
            except Exception:
                pass
        
        return info
    
    @classmethod
    def check_model_ready(cls, models_dir: Path) -> Tuple[bool, str]:
        """
        Verifica se o modelo está pronto para uso.
        
        Args:
            models_dir: Diretório do modelo
        
        Returns:
            Tuple (is_ready, message)
        """
        is_valid, missing, warnings = cls.validate_model_directory(models_dir)
        
        if is_valid:
            message = "Modelo válido e pronto para uso"
            if warnings:
                message += f"\nAvisos: {', '.join(warnings)}"
            return True, message
        else:
            message = f"Modelo incompleto. Arquivos faltando: {', '.join(missing)}"
            return False, message
