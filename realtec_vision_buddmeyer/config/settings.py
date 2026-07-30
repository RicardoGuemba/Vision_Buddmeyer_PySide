# -*- coding: utf-8 -*-
"""
Configurações do sistema usando Pydantic Settings.
Carrega configurações de variáveis de ambiente e arquivo YAML.
"""

from functools import lru_cache
from pathlib import Path
from typing import Optional, List, Dict, Any

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class StreamingSettings(BaseModel):
    """Configurações de streaming de vídeo."""
    
    source_type: str = Field(default="usb", description="Tipo: video, usb, rtsp, gige, gentl. Padrão: usb.")
    video_path: str = Field(default="videos/test.mp4", description="Caminho do arquivo de vídeo")
    usb_camera_index: int = Field(default=0, description="Índice da câmera USB (0 = primeira câmera)")
    rtsp_url: str = Field(default="", description="URL do stream RTSP")
    gige_ip: str = Field(default="", description="IP da câmera GigE")
    gige_port: int = Field(default=3956, description="Porta da câmera GigE")
    gentl_cti_path: str = Field(default="", description="Caminho do arquivo CTI GenTL (ex.: Omron Sentech)")
    gentl_device_index: int = Field(default=0, description="Índice da câmera na lista GenTL (0 = primeira)")
    gentl_max_dimension: int = Field(default=1920, ge=0, le=4096, description="Dimensão máx. do lado maior (px); 0 = sem redimensionar")
    gentl_target_fps: float = Field(default=15.0, ge=1.0, le=60.0, description="FPS alvo do stream GenTL (reduz carga em câmeras de alta resolução)")
    max_frame_buffer_size: int = Field(default=30, description="Tamanho máximo do buffer")
    loop_video: bool = Field(default=True, description="Loop do vídeo")
    
    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, v: str) -> str:
        valid_types = {"video", "usb", "rtsp", "gige", "gentl"}
        if v not in valid_types:
            raise ValueError(f"source_type deve ser um de: {valid_types}")
        return v


class DetectionSettings(BaseModel):
    """Configurações de detecção."""
    
    model_path: str = Field(default="model_best", description="Caminho para modelo local (relativo ao pacote)")
    default_model: str = Field(
        default="model_best",
        description="Modelo padrão (caminho local ou ID do Hugging Face)",
    )
    confidence_threshold: float = Field(default=0.5, ge=0.0, le=1.0, description="Threshold de confiança")
    max_detections: int = Field(default=10, ge=1, description="Máximo de detecções")
    target_classes: Optional[List[str]] = Field(
        default=["Embalagem"],
        description="Classes alvo (null = todas). Padrão: apenas 'Embalagem'",
    )
    inference_fps: int = Field(default=15, ge=1, description="FPS de inferência")
    device: str = Field(default="auto", description="Device: cpu, cuda, mps, auto (mps = Apple Silicon)")

    # Parâmetros específicos de instance segmentation (Mask2Former)
    segmentation_mask_threshold: float = Field(
        default=0.5, ge=0.0, le=1.0,
        description="Threshold de binarização das máscaras Mask2Former",
    )
    segmentation_overlap_mask_area_threshold: float = Field(
        default=0.8, ge=0.0, le=1.0,
        description="Threshold de sobreposição de máscaras (pós-processamento)",
    )
    segmentation_min_mask_pixels: int = Field(
        default=64, ge=1,
        description="Área mínima (px) para aceitar uma máscara e calcular geometria/PCA",
    )
    prioritize_area: bool = Field(
        default=True,
        description="Legado: confiança+área ponderada (preferir best_for_plc no MVP)",
    )
    display_confidence_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confiança mínima para exibir detecção na UI/MJPEG",
    )
    plc_confidence_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confiança mínima para candidato a pick / Mark2",
    )
    
    @field_validator("device")
    @classmethod
    def validate_device(cls, v: str) -> str:
        valid_devices = {"cpu", "cuda", "mps", "auto"}
        if v not in valid_devices:
            raise ValueError(f"device deve ser um de: {valid_devices}")
        return v


# ROI padrão: 25% da área do FOV, centralizado (ex.: 640x480 -> 277x277)
# 25% área = sqrt(0.25)=0.5 -> metade de cada lado; 640*0.5=320, 480*0.5=240
# Para 25% mais conservador: sqrt(76800)≈277 (área 76800 = 25% de 307200)
DEFAULT_ROI_QUARTER_AREA: List[int] = [181, 101, 277, 277]  # x, y, w, h (25% de 640x480)


class PreprocessSettings(BaseModel):
    """Configurações de pré-processamento."""

    profile: str = Field(default="default", description="Perfil de pré-processamento")
    brightness: float = Field(default=0.0, ge=-1.0, le=1.0, description="Ajuste de brilho")
    contrast: float = Field(default=0.0, ge=-1.0, le=1.0, description="Ajuste de contraste")
    roi: Optional[List[int]] = Field(default=None, description="ROI [x, y, width, height] em px")
    roi_unit: str = Field(default="px", description="Unidade ROI: px ou mm")
    roi_calibration_mm_per_px: float = Field(
        default=1.0, ge=0.0001, description="Calibração mm/px: multiplica pixels para obter mm (default 1)"
    )

    @model_validator(mode="before")
    @classmethod
    def _migrate_px_per_mm(cls, data: object) -> object:
        """Migra roi_calibration_px_per_mm (legado) para roi_calibration_mm_per_px."""
        if isinstance(data, dict) and "roi_calibration_px_per_mm" in data:
            data = dict(data)
            px_per_mm = float(data.pop("roi_calibration_px_per_mm"))
            if "roi_calibration_mm_per_px" not in data:
                data["roi_calibration_mm_per_px"] = 1.0 / px_per_mm if px_per_mm else 1.0
        return data


class ServoJointSettings(BaseModel):
    """Limites e zero de uma articulação (base/ombro/cotovelo)."""

    zero: int = Field(default=90, ge=0, le=180)
    direction: int = Field(default=1, description="1 ou -1")
    minimum: int = Field(default=0, ge=0, le=180)
    maximum: int = Field(default=180, ge=0, le=180)


class GripperServoSettings(BaseModel):
    """Configuração da garra."""

    open: int = Field(default=110, ge=0, le=180)
    closed: int = Field(default=60, ge=0, le=180)
    minimum: int = Field(default=50, ge=0, le=180)
    maximum: int = Field(default=120, ge=0, le=180)


class Mark2SerialSettings(BaseModel):
    port: str = Field(default="/dev/cu.usbmodem1101")
    baudrate: int = Field(default=115200)
    timeout_seconds: float = Field(default=5.0, ge=0.5)


class Mark2GeometrySettings(BaseModel):
    link_1_mm: float = Field(default=0.0, ge=0.0)
    link_2_mm: float = Field(default=0.0, ge=0.0)
    shoulder_height_mm: float = Field(default=0.0, ge=0.0)


class Mark2ReferenceSettings(BaseModel):
    origin_x_mm: float = Field(default=0.0)
    origin_y_mm: float = Field(default=0.0)
    rotation_deg: float = Field(default=0.0)


class Mark2WorkspaceSettings(BaseModel):
    min_radius_mm: float = Field(default=0.0, ge=0.0)
    max_radius_mm: float = Field(default=250.0, ge=0.0)
    min_z_mm: float = Field(default=0.0)
    max_z_mm: float = Field(default=200.0)


class Mark2HeightsSettings(BaseModel):
    package_z_mm: float = Field(default=15.0)
    approach_offset_mm: float = Field(default=50.0, ge=0.0)
    drop_z_mm: float = Field(default=15.0)
    drop_x_mm: float = Field(default=100.0)
    drop_y_mm: float = Field(default=0.0)


class Mark2ServosSettings(BaseModel):
    base: ServoJointSettings = Field(default_factory=ServoJointSettings)
    shoulder: ServoJointSettings = Field(default_factory=lambda: ServoJointSettings(direction=-1, minimum=30, maximum=150))
    elbow: ServoJointSettings = Field(default_factory=lambda: ServoJointSettings(minimum=20, maximum=160))
    gripper: GripperServoSettings = Field(default_factory=GripperServoSettings)


class Mark2HomeAnglesSettings(BaseModel):
    base: int = Field(default=90, ge=0, le=180)
    shoulder: int = Field(default=90, ge=0, le=180)
    elbow: int = Field(default=90, ge=0, le=180)
    gripper: int = Field(default=110, ge=0, le=180)


class Mark2DetectionGateSettings(BaseModel):
    minimum_confidence: float = Field(default=0.85, ge=0.0, le=1.0)
    stable_frames: int = Field(default=5, ge=1)
    point_tolerance_px: float = Field(default=4.0, ge=0.0)
    maximum_area_variation: float = Field(default=0.10, ge=0.0, le=1.0)


class Mark2CalibrationSettings(BaseModel):
    homography: Optional[List[List[float]]] = Field(default=None)
    image_points: List[List[float]] = Field(default_factory=list)
    world_points_mm: List[List[float]] = Field(default_factory=list)
    validation_rmse_mm: Optional[float] = Field(default=None)
    max_rmse_mm: float = Field(default=3.0, ge=0.0)
    calibrated_at: Optional[str] = Field(default=None)
    min_homography_points: int = Field(default=4, ge=4)
    min_validation_points: int = Field(default=10, ge=1)


class Mark2OperationSettings(BaseModel):
    mode: str = Field(default="semi", description="manual | semi | auto")
    enabled: bool = Field(default=True)
    smoke_detection_trigger: bool = Field(
        default=True,
        description="Se True: novo movimento da embalagem aciona servo 1x",
    )
    smoke_cooldown_seconds: float = Field(
        default=1.0,
        ge=0.0,
        description="Mínimo entre dois disparos smoke",
    )
    smoke_hold_seconds: float = Field(
        default=1.0,
        ge=0.1,
        le=10.0,
        description="Tempo que o motor permanece no estado activo (s)",
    )
    smoke_movement_tolerance_px: float = Field(
        default=18.0,
        ge=1.0,
        description="Deslocamento mínimo do ponto de pega para considerar novo movimento",
    )
    default_move_speed: int = Field(default=15, ge=1, le=90)

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        valid = {"manual", "semi", "auto"}
        if v not in valid:
            raise ValueError(f"mode deve ser um de: {valid}")
        return v


class Mark2Settings(BaseModel):
    """Configuração do braço Mark2 + Arduino."""

    serial: Mark2SerialSettings = Field(default_factory=Mark2SerialSettings)
    geometry: Mark2GeometrySettings = Field(default_factory=Mark2GeometrySettings)
    reference: Mark2ReferenceSettings = Field(default_factory=Mark2ReferenceSettings)
    workspace: Mark2WorkspaceSettings = Field(default_factory=Mark2WorkspaceSettings)
    heights: Mark2HeightsSettings = Field(default_factory=Mark2HeightsSettings)
    servos: Mark2ServosSettings = Field(default_factory=Mark2ServosSettings)
    home_angles: Mark2HomeAnglesSettings = Field(default_factory=Mark2HomeAnglesSettings)
    detection: Mark2DetectionGateSettings = Field(default_factory=Mark2DetectionGateSettings)
    calibration: Mark2CalibrationSettings = Field(default_factory=Mark2CalibrationSettings)
    operation: Mark2OperationSettings = Field(default_factory=Mark2OperationSettings)

    def save_yaml(self, yaml_path: Path) -> None:
        """Persiste apenas a configuração Mark2."""
        yaml_path.parent.mkdir(parents=True, exist_ok=True)
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(
                self.model_dump(exclude_none=False),
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )

    @classmethod
    def from_yaml(cls, yaml_path: Path) -> "Mark2Settings":
        if not yaml_path.exists():
            return cls()
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls(**data)


class OutputSettings(BaseModel):
    """Configurações de saída de stream (HTTP MJPEG para navegador)."""
    
    rtsp_enabled: bool = Field(default=False, description="Stream HTTP MJPEG habilitado")
    http_port: int = Field(default=8080, description="Porta HTTP para MJPEG (copiar/colar no navegador)")
    http_path: str = Field(default="/stream", description="Path do stream HTTP")


class Settings(BaseSettings):
    """Configurações principais do sistema."""
    
    model_config = SettingsConfigDict(
        env_prefix="BUDDMEYER_",
        env_nested_delimiter="__",
        extra="ignore",
    )
    
    # Logging
    log_level: str = Field(default="INFO", description="Nível de log")
    log_file: Optional[str] = Field(default="logs/realtec_vision.log", description="Arquivo de log")
    
    # Subconfigurations
    streaming: StreamingSettings = Field(default_factory=StreamingSettings)
    detection: DetectionSettings = Field(default_factory=DetectionSettings)
    preprocess: PreprocessSettings = Field(default_factory=PreprocessSettings)
    mark2: Mark2Settings = Field(default_factory=Mark2Settings)
    output: OutputSettings = Field(default_factory=OutputSettings)
    
    @classmethod
    def from_yaml(cls, yaml_path: Path) -> "Settings":
        """Carrega configurações de um arquivo YAML (+ mark2.yaml se existir)."""
        if not yaml_path.exists():
            config_data: Dict[str, Any] = {}
        else:
            with open(yaml_path, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f) or {}

        # Remove blocos legados CIP se ainda existirem no YAML
        for legacy_key in ("cip", "tags", "robot_control"):
            config_data.pop(legacy_key, None)

        mark2_path = yaml_path.parent / "mark2.yaml"
        if mark2_path.exists() and "mark2" not in config_data:
            with open(mark2_path, "r", encoding="utf-8") as f:
                mark2_data = yaml.safe_load(f) or {}
            config_data["mark2"] = mark2_data

        return cls(**config_data)
    
    def to_yaml(self, yaml_path: Path) -> None:
        """Salva configurações em YAML; Mark2 vai para mark2.yaml à parte."""
        yaml_path.parent.mkdir(parents=True, exist_ok=True)
        data = self.model_dump(exclude_none=True)
        mark2_data = data.pop("mark2", None)
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )
        if mark2_data is not None:
            mark2_path = yaml_path.parent / "mark2.yaml"
            with open(mark2_path, "w", encoding="utf-8") as f:
                yaml.dump(
                    mark2_data,
                    f,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False,
                )
    
    def get_base_path(self) -> Path:
        """Retorna o caminho base do projeto."""
        return Path(__file__).parent.parent
    
    def get_models_path(self) -> Path:
        """Retorna o caminho absoluto do diretório de modelos."""
        base_path = self.get_base_path()
        model_path_str = self.detection.model_path
        
        # Se for caminho relativo, resolve em relação ao base_path
        if Path(model_path_str).is_absolute():
            return Path(model_path_str)
        else:
            return base_path / model_path_str


# Cache global para settings
_settings_instance: Optional[Settings] = None


def get_settings(config_path: Optional[Path] = None, reload: bool = False) -> Settings:
    """
    Retorna a instância de configurações.
    
    Args:
        config_path: Caminho para arquivo YAML de configuração
        reload: Se True, recarrega as configurações
    
    Returns:
        Instância de Settings
    """
    global _settings_instance
    
    # Se reload=True, força recarregar
    if reload:
        _settings_instance = None
    
    if _settings_instance is None:
        if config_path is None:
            config_path = Path(__file__).parent / "config.yaml"
        
        if config_path.exists():
            _settings_instance = Settings.from_yaml(config_path)
        else:
            _settings_instance = Settings()
    
    return _settings_instance
