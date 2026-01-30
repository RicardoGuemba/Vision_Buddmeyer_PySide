# -*- coding: utf-8 -*-
"""
Cliente CIP para comunicação com CLP Omron NX102.
"""

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Lock
from typing import Any, Optional, Dict

from PySide6.QtCore import QObject, Signal, QTimer

from config import get_settings
from core.logger import get_logger
from core.metrics import MetricsCollector

from .tag_map import TagMap
from .connection_state import ConnectionState, ConnectionStatus
from .cip_logger import CIPLogger
from .exceptions import CIPConnectionError, CIPTimeoutError, CIPTagError

logger = get_logger("cip.client")


class SimulatedPLC:
    """PLC simulado para desenvolvimento e testes."""
    
    def __init__(self):
        self._tags: Dict[str, Any] = {
            # TAGs de escrita
            "VisionCtrl_VisionReady": False,
            "VisionCtrl_VisionBusy": False,
            "VisionCtrl_VisionError": False,
            "VisionCtrl_Heartbeat": False,
            "PRODUCT_DETECTED": False,
            "CENTROID_X": 0.0,
            "CENTROID_Y": 0.0,
            "CONFIDENCE": 0.0,
            "DETECTION_COUNT": 0,
            "PROCESSING_TIME": 0.0,
            "VisionCtrl_EchoAck": False,
            "VisionCtrl_DataSent": False,
            "VisionCtrl_ReadyForNext": False,
            "SYSTEM_FAULT": False,
            
            # TAGs de leitura
            "ROBOT_ACK": False,
            "ROBOT_READY": True,
            "ROBOT_ERROR": False,
            "RobotStatus_Busy": False,
            "RobotStatus_PickComplete": False,
            "RobotStatus_PlaceComplete": False,
            "RobotCtrl_AuthorizeDetection": True,
            "RobotCtrl_CycleStart": False,
            "RobotCtrl_CycleComplete": False,
            "RobotCtrl_EmergencyStop": False,
            "RobotCtrl_SystemMode": 1,  # Auto
            "SystemStatus_Heartbeat": False,
            "SystemStatus_Mode": 1,
            
            # TAGs de segurança
            "Safety_GateClosed": True,
            "Safety_AreaClear": True,
            "Safety_LightCurtainOK": True,
            "Safety_EmergencyStop": True,
        }
        self._lock = Lock()
        self._ack_delay = 1.5  # Segundos para auto-ACK
    
    def read_variable(self, name: str) -> Any:
        """Lê valor de um TAG."""
        with self._lock:
            return self._tags.get(name, 0)
    
    def write_variable(self, name: str, value: Any) -> None:
        """Escreve valor em um TAG."""
        with self._lock:
            self._tags[name] = value
        
        # Auto ACK após detecção
        if name == "PRODUCT_DETECTED" and value:
            threading.Timer(self._ack_delay, self._auto_ack).start()
    
    def _auto_ack(self) -> None:
        """Simula ACK automático do robô."""
        with self._lock:
            self._tags["ROBOT_ACK"] = True
            logger.debug("simulated_robot_ack")
        
        # Reset após 1 segundo
        threading.Timer(1.0, self._reset_ack).start()
    
    def _reset_ack(self) -> None:
        """Reseta ACK."""
        with self._lock:
            self._tags["ROBOT_ACK"] = False


class CIPClient(QObject):
    """
    Cliente CIP para comunicação com CLP Omron NX102.
    
    Características:
    - Conexão via EtherNet/IP (porta 44818)
    - Leitura e escrita de TAGs
    - Whitelist de TAGs permitidos
    - Reconexão automática com backoff
    - Fallback para modo simulado
    
    Signals:
        connected: Emitido quando conecta
        disconnected: Emitido quando desconecta
        connection_error: Emitido em caso de erro
        tag_read: Emitido quando TAG é lido
        tag_written: Emitido quando TAG é escrito
        state_changed: Emitido quando estado muda
    """
    
    connected = Signal()
    disconnected = Signal()
    connection_error = Signal(str)
    tag_read = Signal(str, object)  # tag_name, value
    tag_written = Signal(str, object)  # tag_name, value
    state_changed = Signal(object)  # ConnectionState
    
    _instance: Optional["CIPClient"] = None
    _lock = Lock()
    
    def __new__(cls) -> "CIPClient":
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
        self._tag_map = TagMap()
        self._cip_logger = CIPLogger()
        self._metrics = MetricsCollector()
        
        # Configurações
        self._ip = self._settings.cip.ip
        self._port = self._settings.cip.port
        self._timeout = self._settings.cip.connection_timeout
        self._simulated = self._settings.cip.simulated
        
        # Estado
        self._plc: Any = None
        self._simulated_plc: Optional[SimulatedPLC] = None
        self._state = ConnectionState(
            status=ConnectionStatus.DISCONNECTED,
            ip=self._ip,
            port=self._port,
        )
        
        # Thread pool para operações síncronas
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cip")
        
        # Heartbeat
        self._heartbeat_timer: Optional[QTimer] = None
        self._heartbeat_value = False
        
        # Reconexão
        self._reconnect_timer: Optional[QTimer] = None
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = self._settings.cip.max_retries
    
    def _reload_connection_config(self) -> None:
        """Recarrega IP, porta e timeout da configuração atual (arquivo/UI)."""
        self._settings = get_settings()
        self._ip = self._settings.cip.ip
        self._port = self._settings.cip.port
        self._timeout = self._settings.cip.connection_timeout
        self._simulated = self._settings.cip.simulated
        self._state.ip = self._ip
        self._state.port = self._port
    
    async def connect(self) -> bool:
        """
        Conecta ao CLP.
        
        Usa sempre a configuração atual (IP/porta) do config/UI ao conectar.
        
        Returns:
            True se conectado com sucesso
        """
        if self._state.is_connected:
            return True
        
        # Recarrega config para usar IP/porta atual (evita IP antigo em memória)
        self._reload_connection_config()
        
        logger.info(
            "cip_connecting",
            ip=self._ip,
            port=self._port,
            timeout=self._timeout,
            simulated=self._simulated,
        )
        
        self._update_state(ConnectionStatus.CONNECTING)
        
        # Tenta conexão real primeiro (se não forçado simulado)
        if not self._simulated:
            try:
                loop = asyncio.get_event_loop()
                self._plc = await loop.run_in_executor(
                    self._executor,
                    self._connect_sync,
                    self._ip,
                    self._timeout,
                )
                
                self._state.last_connected = datetime.now()
                self._update_state(ConnectionStatus.CONNECTED)
                self._cip_logger.log_connect(self._ip, True)
                self._start_heartbeat()
                self.connected.emit()
                
                logger.info("cip_connected", ip=self._ip, port=self._port)
                return True
                
            except Exception as e:
                logger.warning("cip_connect_failed_fallback_simulated", error=str(e))
                self._cip_logger.log_connect(self._ip, False, str(e))
        
        # Fallback para modo simulado
        return await self._connect_simulated()
    
    async def _connect_simulated(self) -> bool:
        """Conecta em modo simulado."""
        self._simulated_plc = SimulatedPLC()
        self._state.is_simulated = True
        self._update_state(ConnectionStatus.SIMULATED)
        self._start_heartbeat()
        self.connected.emit()
        
        logger.info("cip_simulated_mode")
        return True
    
    def _connect_sync(self, ip: str, timeout: float) -> Any:
        """Conecta ao CLP de forma síncrona."""
        try:
            from aphyt import omron
            
            # IMPORTANTE: A classe correta é NSeries
            plc = omron.n_series.NSeries()
            
            if timeout and timeout > 0:
                plc.connect_explicit(ip, connection_timeout=timeout)
            else:
                plc.connect_explicit(ip)
            
            return plc
            
        except ImportError:
            raise CIPConnectionError(
                "Biblioteca aphyt não instalada. Execute: pip install aphyt",
                {"package": "aphyt"}
            )
        except Exception as e:
            raise CIPConnectionError(
                f"Falha ao conectar ao CLP: {e}",
                {"ip": ip, "error": str(e)}
            )
    
    async def disconnect(self) -> None:
        """Desconecta do CLP."""
        self._stop_heartbeat()
        
        if self._plc is not None:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    self._executor,
                    self._plc.close,
                )
            except Exception as e:
                logger.warning("cip_disconnect_error", error=str(e))
            finally:
                self._plc = None
        
        self._simulated_plc = None
        self._update_state(ConnectionStatus.DISCONNECTED)
        self._cip_logger.log_disconnect()
        self.disconnected.emit()
        
        logger.info("cip_disconnected")
    
    async def read_tag(self, logical_name: str) -> Any:
        """
        Lê valor de um TAG.
        
        Args:
            logical_name: Nome lógico do TAG
        
        Returns:
            Valor do TAG
        """
        if not self._state.is_connected:
            raise CIPConnectionError("Não conectado ao CLP")
        
        # Valida TAG
        if not self._tag_map.is_valid_tag(logical_name):
            raise CIPTagError(f"TAG não permitido: {logical_name}")
        
        if not self._tag_map.is_readable(logical_name):
            raise CIPTagError(f"TAG não pode ser lido: {logical_name}")
        
        plc_name = self._tag_map.get_plc_name(logical_name)
        start_time = time.perf_counter()
        
        try:
            if self._simulated_plc:
                value = self._simulated_plc.read_variable(plc_name)
            else:
                loop = asyncio.get_event_loop()
                value = await loop.run_in_executor(
                    self._executor,
                    self._plc.read_variable,
                    plc_name,
                )
            
            duration = (time.perf_counter() - start_time) * 1000
            self._cip_logger.log_read(plc_name, value, True, duration_ms=duration)
            self._metrics.record("cip_response_time", duration)
            
            self.tag_read.emit(logical_name, value)
            return value
            
        except Exception as e:
            duration = (time.perf_counter() - start_time) * 1000
            self._cip_logger.log_read(plc_name, None, False, str(e), duration)
            self._handle_error(str(e), tag_name=plc_name)
            raise CIPTagError(f"Erro ao ler TAG {logical_name}: {e}")
    
    async def write_tag(self, logical_name: str, value: Any) -> bool:
        """
        Escreve valor em um TAG.
        
        Args:
            logical_name: Nome lógico do TAG
            value: Valor a escrever
        
        Returns:
            True se escrito com sucesso
        """
        if not self._state.is_connected:
            raise CIPConnectionError("Não conectado ao CLP")
        
        # Valida TAG
        if not self._tag_map.is_valid_tag(logical_name):
            raise CIPTagError(f"TAG não permitido: {logical_name}")
        
        if not self._tag_map.is_writable(logical_name):
            raise CIPTagError(f"TAG não pode ser escrito: {logical_name}")
        
        if not self._tag_map.validate_value(logical_name, value):
            raise CIPTagError(f"Valor inválido para TAG {logical_name}: {value}")
        
        plc_name = self._tag_map.get_plc_name(logical_name)
        start_time = time.perf_counter()
        
        try:
            if self._simulated_plc:
                self._simulated_plc.write_variable(plc_name, value)
            else:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    self._executor,
                    self._plc.write_variable,
                    plc_name,
                    value,
                )
            
            duration = (time.perf_counter() - start_time) * 1000
            self._cip_logger.log_write(plc_name, value, True, duration_ms=duration)
            self._metrics.record("cip_response_time", duration)
            
            self.tag_written.emit(logical_name, value)
            return True
            
        except Exception as e:
            duration = (time.perf_counter() - start_time) * 1000
            self._cip_logger.log_write(plc_name, value, False, str(e), duration)
            self._handle_error(str(e), tag_name=plc_name)
            raise CIPTagError(f"Erro ao escrever TAG {logical_name}: {e}")
    
    async def write_detection_result(
        self,
        detected: bool,
        centroid_x: float = 0.0,
        centroid_y: float = 0.0,
        confidence: float = 0.0,
        detection_count: int = 0,
        processing_time: float = 0.0,
    ) -> bool:
        """
        Escreve resultado de detecção nos TAGs do CLP.
        
        Args:
            detected: Se produto foi detectado
            centroid_x: Coordenada X do centroide
            centroid_y: Coordenada Y do centroide
            confidence: Confiança (0-1)
            detection_count: Número de detecções
            processing_time: Tempo de processamento (ms)
        
        Returns:
            True se todos os TAGs foram escritos
        """
        try:
            await self.write_tag("ProductDetected", detected)
            await self.write_tag("CentroidX", centroid_x)
            await self.write_tag("CentroidY", centroid_y)
            await self.write_tag("Confidence", confidence)
            await self.write_tag("DetectionCount", detection_count)
            await self.write_tag("ProcessingTime", processing_time)
            await self.write_tag("VisionDataSent", True)
            
            logger.info(
                "detection_result_written",
                detected=detected,
                centroid=(centroid_x, centroid_y),
                confidence=confidence,
            )
            return True
            
        except Exception as e:
            logger.error("detection_result_write_failed", error=str(e))
            return False
    
    async def read_robot_ack(self) -> bool:
        """Lê o ACK do robô."""
        return await self.read_tag("RobotAck")
    
    async def set_vision_ready(self, ready: bool) -> bool:
        """Define se o sistema de visão está pronto."""
        return await self.write_tag("VisionReady", ready)
    
    async def set_vision_echo_ack(self, ack: bool) -> bool:
        """Define echo de confirmação."""
        return await self.write_tag("VisionEchoAck", ack)
    
    async def set_ready_for_next(self, ready: bool) -> bool:
        """Define pronto para próximo ciclo."""
        return await self.write_tag("VisionReadyForNext", ready)
    
    def get_status(self) -> Dict[str, Any]:
        """Retorna status da conexão."""
        return {
            **self._state.to_dict(),
            "cip_stats": self._cip_logger.get_stats(),
            "error_rate": self._cip_logger.get_error_rate(),
        }
    
    def _update_state(self, status: ConnectionStatus) -> None:
        """Atualiza estado da conexão."""
        self._state.status = status
        self.state_changed.emit(self._state)
    
    def _handle_error(self, error: str, tag_name: Optional[str] = None) -> None:
        """Trata erros de comunicação. Registra IP e tag para rastreio."""
        self._state.error_count += 1
        self._state.last_error = error
        self._metrics.increment("cip_errors")
        
        logger.error(
            "cip_error",
            ip=self._state.ip,
            port=self._state.port,
            tag=tag_name,
            error=error,
        )
        
        # Marca como degradado se muitos erros
        if self._state.error_count > 5 and self._state.status == ConnectionStatus.CONNECTED:
            self._update_state(ConnectionStatus.DEGRADED)
        
        self.connection_error.emit(error)
    
    def _start_heartbeat(self) -> None:
        """Inicia heartbeat."""
        if self._heartbeat_timer is not None:
            return
        
        interval = int(self._settings.cip.heartbeat_interval * 1000)
        self._heartbeat_timer = QTimer(self)
        self._heartbeat_timer.timeout.connect(self._send_heartbeat)
        self._heartbeat_timer.start(interval)
    
    def _stop_heartbeat(self) -> None:
        """Para heartbeat."""
        if self._heartbeat_timer is not None:
            self._heartbeat_timer.stop()
            self._heartbeat_timer.deleteLater()
            self._heartbeat_timer = None
    
    def _send_heartbeat(self) -> None:
        """Envia heartbeat."""
        self._heartbeat_value = not self._heartbeat_value
        
        # Usa run_coroutine para executar async em thread Qt
        asyncio.create_task(self.write_tag("VisionHeartbeat", self._heartbeat_value))
    
    @property
    def is_connected(self) -> bool:
        """Verifica se está conectado."""
        return self._state.is_connected
    
    @property
    def is_simulated(self) -> bool:
        """Verifica se está em modo simulado."""
        return self._state.is_simulated
    
    @property
    def state(self) -> ConnectionState:
        """Retorna estado atual."""
        return self._state


# Função de conveniência
def get_cip_client() -> CIPClient:
    """Retorna a instância do cliente CIP."""
    return CIPClient()
