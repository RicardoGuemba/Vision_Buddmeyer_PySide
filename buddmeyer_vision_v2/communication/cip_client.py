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

from .tag_map import TagMap, TagType
from .connection_state import ConnectionState, ConnectionStatus
from .cip_logger import CIPLogger
from .exceptions import CIPConnectionError, CIPTimeoutError, CIPTagError

logger = get_logger("cip.client")


class SimulatedPLC:
    """
    PLC simulado com ciclo completo de pick-and-place.
    
    Simula um robo conectado ao CLP que responde ao handshake:
      1. Visao envia PRODUCT_DETECTED -> Robo responde ROBOT_ACK
      2. Visao confirma EchoAck       -> Robo executa Pick (RobotPickComplete)
      3. Apos Pick                     -> Robo executa Place (RobotPlaceComplete)
      4. Apos Place                    -> CLP sinaliza ciclo (PlcCycleStart)
      5. Visao envia ReadyForNext      -> Flags resetadas para novo ciclo
    
    Delays simulam tempos reais de movimentacao do robo.
    """
    
    def __init__(self):
        self._tags: Dict[str, Any] = {
            # TAGs de escrita (Visao -> CLP)
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
            
            # TAGs de leitura (CLP/Robo -> Visao)
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
            
            # TAGs de seguranca
            "Safety_GateClosed": True,
            "Safety_AreaClear": True,
            "Safety_LightCurtainOK": True,
            "Safety_EmergencyStop": True,
        }
        self._lock = Lock()
        
        # Delays simulados (segundos) — tempos tipicos de expedicao
        self._ack_delay = 1.5       # Tempo para robo/CLP reconhecer deteccao
        self._pick_delay = 4.0      # Tempo tipico de pick em expedicao
        self._place_delay = 5.0     # Tempo tipico de place em expedicao
        self._cycle_end_delay = 1.0 # Tempo para CLP sinalizar fim de ciclo
    
    def read_variable(self, name: str) -> Any:
        """Le valor de um TAG."""
        with self._lock:
            return self._tags.get(name, 0)
    
    def write_variable(self, name: str, value: Any) -> None:
        """Escreve valor em um TAG e dispara simulacao de robo conforme handshake."""
        with self._lock:
            self._tags[name] = value
        
        # --- Handshake reativo do robo simulado ---
        
        # Etapa 1: Visao detectou produto -> Robo envia ACK
        if name == "PRODUCT_DETECTED" and value:
            logger.debug("sim_robot: produto detectado, enviando ACK em %.1fs", self._ack_delay)
            threading.Timer(self._ack_delay, self._simulate_robot_ack).start()
        
        # Etapa 2: Visao confirmou ACK (EchoAck) -> Robo inicia Pick
        elif name == "VisionCtrl_EchoAck" and value:
            logger.debug("sim_robot: EchoAck recebido, executando PICK em %.1fs", self._pick_delay)
            threading.Timer(self._pick_delay, self._simulate_pick_complete).start()
        
        # Etapa 5: Visao pronta para proximo ciclo -> Reset de flags
        elif name == "VisionCtrl_ReadyForNext" and value:
            logger.debug("sim_robot: ReadyForNext recebido, resetando flags")
            self._reset_robot_flags()
    
    def _simulate_robot_ack(self) -> None:
        """Robo reconhece a deteccao (ACK)."""
        with self._lock:
            self._tags["ROBOT_ACK"] = True
            self._tags["RobotStatus_Busy"] = True
        logger.debug("sim_robot: ROBOT_ACK = True")
    
    def _simulate_pick_complete(self) -> None:
        """Robo concluiu o pick."""
        with self._lock:
            self._tags["RobotStatus_PickComplete"] = True
        logger.debug("sim_robot: PickComplete = True, executando PLACE em %.1fs", self._place_delay)
        # Apos pick, inicia place
        threading.Timer(self._place_delay, self._simulate_place_complete).start()
    
    def _simulate_place_complete(self) -> None:
        """Robo concluiu o place."""
        with self._lock:
            self._tags["RobotStatus_PlaceComplete"] = True
            self._tags["RobotStatus_Busy"] = False
        logger.debug("sim_robot: PlaceComplete = True, sinalizando ciclo em %.1fs", self._cycle_end_delay)
        # Apos place, CLP sinaliza fim de ciclo
        threading.Timer(self._cycle_end_delay, self._simulate_cycle_complete).start()
    
    def _simulate_cycle_complete(self) -> None:
        """CLP sinaliza que o ciclo esta completo."""
        with self._lock:
            self._tags["RobotCtrl_CycleStart"] = True
        logger.debug("sim_robot: CycleStart = True (ciclo completo)")
    
    def _reset_robot_flags(self) -> None:
        """Reseta todas as flags do robo para novo ciclo."""
        with self._lock:
            self._tags["ROBOT_ACK"] = False
            self._tags["RobotStatus_Busy"] = False
            self._tags["RobotStatus_PickComplete"] = False
            self._tags["RobotStatus_PlaceComplete"] = False
            self._tags["RobotCtrl_CycleStart"] = False
            self._tags["PRODUCT_DETECTED"] = False
            self._tags["VisionCtrl_EchoAck"] = False
            self._tags["VisionCtrl_DataSent"] = False
            self._tags["VisionCtrl_ReadyForNext"] = False
        logger.debug("sim_robot: flags resetadas para novo ciclo")


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
                # NSeries da aphyt não tem método close(); tenta close_explicit se existir
                close_method = getattr(self._plc, "close_explicit", None)
                if close_method is None:
                    close_method = getattr(self._plc, "close", None)
                if close_method is not None and callable(close_method):
                    await loop.run_in_executor(self._executor, close_method)
                # Se não houver método, apenas descarta a referência
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
        io_retries = getattr(self._settings.cip, "io_retries", 0) or 0
        max_attempts = 1 + io_retries
        
        for attempt in range(max_attempts):
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
                
            except RecursionError as e:
                # Bug conhecido na biblioteca aphyt: RecursionError em certos TAGs
                # Trata como erro fatal e retorna valor padrão seguro baseado no tipo
                duration = (time.perf_counter() - start_time) * 1000
                error_msg = f"RecursionError aphyt (bug na biblioteca): retornando valor padrão"
                self._cip_logger.log_read(plc_name, None, False, error_msg, duration)
                
                logger.error(
                    "cip_read_recursion_aphyt_bug", 
                    tag=plc_name,
                    error=str(e)[:50]
                )
                
                # Define valor padrão seguro baseado no tipo esperado do TAG
                definition = self._tag_map.get_definition(logical_name)
                if definition:
                    # Retorna valor padrão do tipo
                    if definition.tag_type == TagType.BOOL:
                        safe_value = False  # Padrão seguro para booleano
                    elif definition.tag_type == TagType.INT:
                        safe_value = 0
                    elif definition.tag_type == TagType.REAL:
                        safe_value = 0.0
                    else:
                        safe_value = None
                    
                    logger.warning(
                        "cip_read_recursion_returning_default",
                        tag=plc_name,
                        default_value=safe_value
                    )
                    self.tag_read.emit(logical_name, safe_value)
                    return safe_value
                else:
                    # Se não conseguir determinar o tipo, relança o erro
                    raise CIPTagError(f"RecursionError ao ler TAG {logical_name}: bug na biblioteca aphyt")
            
            except Exception as e:
                duration = (time.perf_counter() - start_time) * 1000
                self._cip_logger.log_read(plc_name, None, False, str(e), duration)
                if attempt < max_attempts - 1:
                    logger.warning("cip_read_retry", tag=plc_name, attempt=attempt + 1, error=str(e))
                    await asyncio.sleep(0.2)
                else:
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
        io_retries = getattr(self._settings.cip, "io_retries", 0) or 0
        max_attempts = 1 + io_retries
        
        for attempt in range(max_attempts):
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
                if attempt < max_attempts - 1:
                    logger.warning("cip_write_retry", tag=plc_name, attempt=attempt + 1, error=str(e))
                    await asyncio.sleep(0.2)
                else:
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
            if getattr(self._settings.cip, "auto_reconnect", True):
                self._schedule_reconnect()
        
        self.connection_error.emit(error)
    
    def _schedule_reconnect(self) -> None:
        """Agenda tentativa de reconexão após retry_interval (RNF-02)."""
        if self._reconnect_timer is not None:
            return
        interval_ms = int(self._settings.cip.retry_interval * 1000)
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._on_reconnect_timer)
        self._reconnect_timer.start(interval_ms)
        logger.info("cip_reconnect_scheduled", interval_s=self._settings.cip.retry_interval)
    
    def _on_reconnect_timer(self) -> None:
        """Tentativa de reconexão (chamado pelo timer)."""
        if self._reconnect_timer is not None:
            self._reconnect_timer.stop()
            self._reconnect_timer.deleteLater()
            self._reconnect_timer = None
        if not self._state.is_connected and self._state.status != ConnectionStatus.CONNECTING:
            asyncio.create_task(self._try_reconnect())
    
    async def _try_reconnect(self) -> None:
        """Desconecta e tenta reconectar (usado por reconexão automática)."""
        self._reconnect_attempts += 1
        max_attempts = self._settings.cip.max_retries
        if self._reconnect_attempts > max_attempts:
            logger.warning("cip_reconnect_abandoned", attempts=self._reconnect_attempts)
            return
        await self.disconnect()
        await asyncio.sleep(0.5)
        await self.connect()
        if self._state.is_connected:
            self._reconnect_attempts = 0
            logger.info("cip_reconnect_ok")
    
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
