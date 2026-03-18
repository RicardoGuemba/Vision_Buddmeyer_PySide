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
    
    model_path: str = Field(default="models", description="Caminho para modelos locais")
    default_model: str = Field(default="PekingU/rtdetr_r50vd", description="Modelo padrão")
    confidence_threshold: float = Field(default=0.5, ge=0.0, le=1.0, description="Threshold de confiança")
    max_detections: int = Field(default=10, ge=1, description="Máximo de detecções")
    target_classes: Optional[List[str]] = Field(default=None, description="Classes alvo (null = todas)")
    inference_fps: int = Field(default=15, ge=1, description="FPS de inferência")
    device: str = Field(default="auto", description="Device: cpu, cuda, mps, auto (mps = Apple Silicon)")
    
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


class CIPSettings(BaseModel):
    """Configurações de comunicação CIP."""
    
    ip: str = Field(default="187.99.124.229", description="IP do CLP")
    port: int = Field(default=44818, description="Porta CIP")
    connection_timeout: float = Field(default=10.0, ge=1.0, description="Timeout de conexão (s)")
    timeout_ms: int = Field(default=10000, ge=1000, description="Timeout de operação (ms)")
    retry_interval: float = Field(default=2.0, ge=0.5, description="Intervalo de reconexão (s)")
    max_retries: int = Field(default=3, ge=0, description="Máximo de tentativas de conexão")
    io_retries: int = Field(default=2, ge=0, le=5, description="Tentativas de leitura/escrita por operação")
    simulated: bool = Field(default=False, description="Modo simulado")
    heartbeat_interval: float = Field(default=1.0, ge=0.1, description="Intervalo de heartbeat (s)")
    auto_reconnect: bool = Field(default=True, description="Reconexão automática quando degradado/desconectado")


class RobotControlSettings(BaseModel):
    """Configurações da máquina de estados do controle robô/CLP."""
    
    ack_timeout: float = Field(default=5.0, ge=1.0, description="Timeout para ACK do robô (s)")
    pick_timeout: float = Field(default=30.0, ge=5.0, description="Timeout para pick (s)")
    place_timeout: float = Field(default=30.0, ge=5.0, description="Timeout para place (s)")
    authorization_timeout: float = Field(default=30.0, ge=5.0, description="Timeout para autorização CLP (s)")
    bypass_authorization: bool = Field(default=False, description="Bypass autorização CLP (para testes)")


class TagSettings(BaseModel):
    """Mapeamento de TAGs CLP."""
    
    # TAGs de escrita (Visão → CLP)
    VisionReady: str = Field(default="VisionCtrl_VisionReady")
    VisionBusy: str = Field(default="VisionCtrl_VisionBusy")
    VisionError: str = Field(default="VisionCtrl_VisionError")
    VisionHeartbeat: str = Field(default="VisionCtrl_Heartbeat")
    ProductDetected: str = Field(default="PRODUCT_DETECTED")
    CentroidX: str = Field(default="CENTROID_X")
    CentroidY: str = Field(default="CENTROID_Y")
    Confidence: str = Field(default="CONFIDENCE")
    DetectionCount: str = Field(default="DETECTION_COUNT")
    ProcessingTime: str = Field(default="PROCESSING_TIME")
    VisionEchoAck: str = Field(default="VisionCtrl_EchoAck")
    VisionDataSent: str = Field(default="VisionCtrl_DataSent")
    VisionReadyForNext: str = Field(default="VisionCtrl_ReadyForNext")
    SystemFault: str = Field(default="SYSTEM_FAULT")
    
    # TAGs de leitura (CLP → Visão)
    RobotAck: str = Field(default="ROBOT_ACK")
    RobotReady: str = Field(default="ROBOT_READY")
    RobotError: str = Field(default="ROBOT_ERROR")
    RobotBusy: str = Field(default="RobotStatus_Busy")
    RobotPickComplete: str = Field(default="RobotStatus_PickComplete")
    RobotPlaceComplete: str = Field(default="RobotStatus_PlaceComplete")
    PlcAuthorizeDetection: str = Field(default="RobotCtrl_AuthorizeDetection")
    PlcCycleStart: str = Field(default="RobotCtrl_CycleStart")
    PlcCycleComplete: str = Field(default="RobotCtrl_CycleComplete")
    PlcEmergencyStop: str = Field(default="RobotCtrl_EmergencyStop")
    PlcSystemMode: str = Field(default="RobotCtrl_SystemMode")
    Heartbeat: str = Field(default="SystemStatus_Heartbeat")
    SystemMode: str = Field(default="SystemStatus_Mode")
    
    # TAGs de segurança
    SafetyGateClosed: str = Field(default="Safety_GateClosed")
    SafetyAreaClear: str = Field(default="Safety_AreaClear")
    SafetyLightCurtainOK: str = Field(default="Safety_LightCurtainOK")
    SafetyEmergencyStop: str = Field(default="Safety_EmergencyStop")


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
    cip: CIPSettings = Field(default_factory=CIPSettings)
    robot_control: RobotControlSettings = Field(default_factory=RobotControlSettings)
    tags: TagSettings = Field(default_factory=TagSettings)
    output: OutputSettings = Field(default_factory=OutputSettings)
    
    @classmethod
    def from_yaml(cls, yaml_path: Path) -> "Settings":
        """Carrega configurações de um arquivo YAML."""
        if not yaml_path.exists():
            return cls()
        
        with open(yaml_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f) or {}
        
        return cls(**config_data)
    
    def to_yaml(self, yaml_path: Path) -> None:
        """Salva configurações em um arquivo YAML."""
        yaml_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(
                self.model_dump(exclude_none=True),
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
