# -*- coding: utf-8 -*-
"""
Mapeamento de TAGs CIP.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, Optional, Set

from config import get_settings


class TagType(str, Enum):
    """Tipos de dados de TAG."""
    
    BOOL = "bool"
    INT = "int"
    REAL = "real"
    STRING = "string"


class TagDirection(str, Enum):
    """Direção do TAG."""
    
    READ = "read"      # CLP → Visão
    WRITE = "write"    # Visão → CLP
    BOTH = "both"


@dataclass
class TagDefinition:
    """Definição de um TAG."""
    
    logical_name: str
    plc_name: str
    tag_type: TagType
    direction: TagDirection
    description: str = ""
    default_value: Any = None
    
    def validate_value(self, value: Any) -> bool:
        """Valida se o valor é compatível com o tipo."""
        if self.tag_type == TagType.BOOL:
            return isinstance(value, bool)
        elif self.tag_type == TagType.INT:
            return isinstance(value, int)
        elif self.tag_type == TagType.REAL:
            return isinstance(value, (int, float))
        elif self.tag_type == TagType.STRING:
            return isinstance(value, str)
        return True


class TagMap:
    """
    Mapeamento de TAGs lógicos para nomes do CLP.
    
    Implementa whitelist para segurança.
    """
    
    # Definições de TAGs
    DEFINITIONS: Dict[str, TagDefinition] = {
        # TAGs de escrita (Visão → CLP)
        "VisionReady": TagDefinition(
            logical_name="VisionReady",
            plc_name="VisionCtrl_VisionReady",
            tag_type=TagType.BOOL,
            direction=TagDirection.WRITE,
            description="Sistema de visão pronto",
            default_value=False,
        ),
        "VisionBusy": TagDefinition(
            logical_name="VisionBusy",
            plc_name="VisionCtrl_VisionBusy",
            tag_type=TagType.BOOL,
            direction=TagDirection.WRITE,
            description="Sistema processando",
        ),
        "VisionError": TagDefinition(
            logical_name="VisionError",
            plc_name="VisionCtrl_VisionError",
            tag_type=TagType.BOOL,
            direction=TagDirection.WRITE,
            description="Erro no sistema",
        ),
        "VisionHeartbeat": TagDefinition(
            logical_name="VisionHeartbeat",
            plc_name="VisionCtrl_Heartbeat",
            tag_type=TagType.BOOL,
            direction=TagDirection.WRITE,
            description="Heartbeat (toggle)",
        ),
        "ProductDetected": TagDefinition(
            logical_name="ProductDetected",
            plc_name="PRODUCT_DETECTED",
            tag_type=TagType.BOOL,
            direction=TagDirection.WRITE,
            description="Produto detectado",
        ),
        "CentroidX": TagDefinition(
            logical_name="CentroidX",
            plc_name="CENTROID_X",
            tag_type=TagType.REAL,
            direction=TagDirection.WRITE,
            description="Coordenada X do centroide",
        ),
        "CentroidY": TagDefinition(
            logical_name="CentroidY",
            plc_name="CENTROID_Y",
            tag_type=TagType.REAL,
            direction=TagDirection.WRITE,
            description="Coordenada Y do centroide",
        ),
        "CentroidAngle": TagDefinition(
            logical_name="CentroidAngle",
            plc_name="CENTROID_ANGLE",
            tag_type=TagType.REAL,
            direction=TagDirection.WRITE,
            description="Ângulo do eixo maior da embalagem (graus, [0, 180))",
        ),
        "ObjectArea": TagDefinition(
            logical_name="ObjectArea",
            plc_name="OBJECT_AREA",
            tag_type=TagType.REAL,
            direction=TagDirection.WRITE,
            description="Área do objeto (px² ou mm², conforme calibração)",
        ),
        "Confidence": TagDefinition(
            logical_name="Confidence",
            plc_name="CONFIDENCE",
            tag_type=TagType.REAL,
            direction=TagDirection.WRITE,
            description="Confiança (0-1)",
        ),
        "DetectionCount": TagDefinition(
            logical_name="DetectionCount",
            plc_name="DETECTION_COUNT",
            tag_type=TagType.INT,
            direction=TagDirection.WRITE,
            description="Contador de detecções",
        ),
        "ProcessingTime": TagDefinition(
            logical_name="ProcessingTime",
            plc_name="PROCESSING_TIME",
            tag_type=TagType.REAL,
            direction=TagDirection.WRITE,
            description="Tempo de processamento (ms)",
        ),
        "VisionEchoAck": TagDefinition(
            logical_name="VisionEchoAck",
            plc_name="VisionCtrl_EchoAck",
            tag_type=TagType.BOOL,
            direction=TagDirection.WRITE,
            description="Echo de confirmação",
        ),
        "VisionDataSent": TagDefinition(
            logical_name="VisionDataSent",
            plc_name="VisionCtrl_DataSent",
            tag_type=TagType.BOOL,
            direction=TagDirection.WRITE,
            description="Dados enviados",
        ),
        "VisionReadyForNext": TagDefinition(
            logical_name="VisionReadyForNext",
            plc_name="VisionCtrl_ReadyForNext",
            tag_type=TagType.BOOL,
            direction=TagDirection.WRITE,
            description="Pronto para próximo ciclo",
        ),
        "SystemFault": TagDefinition(
            logical_name="SystemFault",
            plc_name="SYSTEM_FAULT",
            tag_type=TagType.BOOL,
            direction=TagDirection.WRITE,
            description="Falha do sistema",
        ),
        
        # TAGs de leitura (CLP → Visão)
        "RobotAck": TagDefinition(
            logical_name="RobotAck",
            plc_name="ROBOT_ACK",
            tag_type=TagType.BOOL,
            direction=TagDirection.READ,
            description="ACK do robô",
        ),
        "RobotReady": TagDefinition(
            logical_name="RobotReady",
            plc_name="ROBOT_READY",
            tag_type=TagType.BOOL,
            direction=TagDirection.READ,
            description="Robô pronto",
        ),
        "RobotError": TagDefinition(
            logical_name="RobotError",
            plc_name="ROBOT_ERROR",
            tag_type=TagType.BOOL,
            direction=TagDirection.READ,
            description="Erro no robô",
        ),
        "RobotBusy": TagDefinition(
            logical_name="RobotBusy",
            plc_name="RobotStatus_Busy",
            tag_type=TagType.BOOL,
            direction=TagDirection.READ,
            description="Robô executando movimento",
        ),
        "RobotPickComplete": TagDefinition(
            logical_name="RobotPickComplete",
            plc_name="RobotStatus_PickComplete",
            tag_type=TagType.BOOL,
            direction=TagDirection.READ,
            description="Pick completado",
        ),
        "RobotPlaceComplete": TagDefinition(
            logical_name="RobotPlaceComplete",
            plc_name="RobotStatus_PlaceComplete",
            tag_type=TagType.BOOL,
            direction=TagDirection.READ,
            description="Place completado",
        ),
        "PlcAuthorizeDetection": TagDefinition(
            logical_name="PlcAuthorizeDetection",
            plc_name="RobotCtrl_AuthorizeDetection",
            tag_type=TagType.BOOL,
            direction=TagDirection.READ,
            description="CLP autoriza detecção",
        ),
        "PlcCycleStart": TagDefinition(
            logical_name="PlcCycleStart",
            plc_name="RobotCtrl_CycleStart",
            tag_type=TagType.BOOL,
            direction=TagDirection.READ,
            description="CLP solicita novo ciclo",
        ),
        "PlcCycleComplete": TagDefinition(
            logical_name="PlcCycleComplete",
            plc_name="RobotCtrl_CycleComplete",
            tag_type=TagType.BOOL,
            direction=TagDirection.READ,
            description="Ciclo completo",
        ),
        "PlcEmergencyStop": TagDefinition(
            logical_name="PlcEmergencyStop",
            plc_name="RobotCtrl_EmergencyStop",
            tag_type=TagType.BOOL,
            direction=TagDirection.READ,
            description="Parada de emergência",
        ),
        "PlcSystemMode": TagDefinition(
            logical_name="PlcSystemMode",
            plc_name="RobotCtrl_SystemMode",
            tag_type=TagType.INT,
            direction=TagDirection.READ,
            description="Modo (0=Manual, 1=Auto, 2=Manutenção)",
        ),
        "Heartbeat": TagDefinition(
            logical_name="Heartbeat",
            plc_name="SystemStatus_Heartbeat",
            tag_type=TagType.BOOL,
            direction=TagDirection.READ,
            description="Heartbeat do sistema",
        ),
        "SystemMode": TagDefinition(
            logical_name="SystemMode",
            plc_name="SystemStatus_Mode",
            tag_type=TagType.INT,
            direction=TagDirection.READ,
            description="Modo do sistema",
        ),
        
        # TAGs de segurança
        "SafetyGateClosed": TagDefinition(
            logical_name="SafetyGateClosed",
            plc_name="Safety_GateClosed",
            tag_type=TagType.BOOL,
            direction=TagDirection.READ,
            description="Portão fechado",
        ),
        "SafetyAreaClear": TagDefinition(
            logical_name="SafetyAreaClear",
            plc_name="Safety_AreaClear",
            tag_type=TagType.BOOL,
            direction=TagDirection.READ,
            description="Área livre",
        ),
        "SafetyLightCurtainOK": TagDefinition(
            logical_name="SafetyLightCurtainOK",
            plc_name="Safety_LightCurtainOK",
            tag_type=TagType.BOOL,
            direction=TagDirection.READ,
            description="Cortina de luz OK",
        ),
        "SafetyEmergencyStop": TagDefinition(
            logical_name="SafetyEmergencyStop",
            plc_name="Safety_EmergencyStop",
            tag_type=TagType.BOOL,
            direction=TagDirection.READ,
            description="Emergência não ativa",
        ),
    }
    
    def __init__(self):
        """Inicializa o mapeamento com configurações."""
        self._settings = get_settings()
        self._custom_mappings: Dict[str, str] = {}
        
        # Carrega mapeamentos customizados da configuração
        self._load_custom_mappings()
    
    def _load_custom_mappings(self) -> None:
        """Carrega mapeamentos customizados da configuração."""
        tags_settings = self._settings.tags
        
        for field_name in dir(tags_settings):
            if not field_name.startswith("_"):
                value = getattr(tags_settings, field_name)
                if isinstance(value, str) and value:
                    self._custom_mappings[field_name] = value
    
    def get_plc_name(self, logical_name: str) -> str:
        """
        Obtém o nome do TAG no CLP.
        
        Args:
            logical_name: Nome lógico do TAG
        
        Returns:
            Nome do TAG no CLP
        """
        # Verifica mapeamento customizado primeiro
        if logical_name in self._custom_mappings:
            return self._custom_mappings[logical_name]
        
        # Verifica definição padrão
        if logical_name in self.DEFINITIONS:
            return self.DEFINITIONS[logical_name].plc_name
        
        # Retorna o nome lógico como fallback
        return logical_name
    
    def get_definition(self, logical_name: str) -> Optional[TagDefinition]:
        """Obtém definição de um TAG."""
        return self.DEFINITIONS.get(logical_name)
    
    def is_valid_tag(self, logical_name: str) -> bool:
        """Verifica se é um TAG válido (whitelist)."""
        return logical_name in self.DEFINITIONS or logical_name in self._custom_mappings
    
    def is_writable(self, logical_name: str) -> bool:
        """Verifica se TAG pode ser escrito."""
        definition = self.DEFINITIONS.get(logical_name)
        if definition:
            return definition.direction in (TagDirection.WRITE, TagDirection.BOTH)
        return True  # Permite TAGs customizados
    
    def is_readable(self, logical_name: str) -> bool:
        """Verifica se TAG pode ser lido."""
        definition = self.DEFINITIONS.get(logical_name)
        if definition:
            return definition.direction in (TagDirection.READ, TagDirection.BOTH)
        return True  # Permite TAGs customizados
    
    def get_all_write_tags(self) -> Set[str]:
        """Retorna todos os TAGs de escrita."""
        return {
            name for name, defn in self.DEFINITIONS.items()
            if defn.direction in (TagDirection.WRITE, TagDirection.BOTH)
        }
    
    def get_all_read_tags(self) -> Set[str]:
        """Retorna todos os TAGs de leitura."""
        return {
            name for name, defn in self.DEFINITIONS.items()
            if defn.direction in (TagDirection.READ, TagDirection.BOTH)
        }
    
    def validate_value(self, logical_name: str, value: Any) -> bool:
        """Valida valor para um TAG."""
        definition = self.DEFINITIONS.get(logical_name)
        if definition:
            return definition.validate_value(value)
        return True
