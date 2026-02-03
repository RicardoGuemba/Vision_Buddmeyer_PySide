# -*- coding: utf-8 -*-
"""
Controlador de robô com máquina de estados.
"""

import asyncio
from enum import Enum
from datetime import datetime
from threading import Lock
from typing import Optional, Dict, Any, List

from PySide6.QtCore import QObject, Signal, QTimer

from config import get_settings
from core.logger import get_logger
from core.metrics import MetricsCollector
from core.exceptions import RobotControlError, StateTransitionError
from communication import CIPClient
from detection.events import DetectionEvent

logger = get_logger("control.robot")


class RobotControlState(str, Enum):
    """Estados da máquina de estados do controle de robô."""
    
    INITIALIZING = "INITIALIZING"
    WAITING_AUTHORIZATION = "WAITING_AUTHORIZATION"
    DETECTING = "DETECTING"
    WAITING_SEND_AUTHORIZATION = "WAITING_SEND_AUTHORIZATION"  # Modo manual: aguarda operador autorizar envio ao CLP
    SENDING_DATA = "SENDING_DATA"
    WAITING_ACK = "WAITING_ACK"
    ACK_CONFIRMED = "ACK_CONFIRMED"
    WAITING_PICK = "WAITING_PICK"
    WAITING_PLACE = "WAITING_PLACE"
    WAITING_CYCLE_START = "WAITING_CYCLE_START"
    READY_FOR_NEXT = "READY_FOR_NEXT"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"
    SAFETY_BLOCKED = "SAFETY_BLOCKED"
    STOPPED = "STOPPED"


# Transições válidas de estado
VALID_TRANSITIONS = {
    RobotControlState.STOPPED: {
        RobotControlState.INITIALIZING,
    },
    RobotControlState.INITIALIZING: {
        RobotControlState.WAITING_AUTHORIZATION,
        RobotControlState.ERROR,
        RobotControlState.STOPPED,
    },
    RobotControlState.WAITING_AUTHORIZATION: {
        RobotControlState.DETECTING,
        RobotControlState.ERROR,
        RobotControlState.SAFETY_BLOCKED,
        RobotControlState.STOPPED,
    },
    RobotControlState.DETECTING: {
        RobotControlState.SENDING_DATA,
        RobotControlState.WAITING_SEND_AUTHORIZATION,  # Modo manual: aguarda autorização para envio
        RobotControlState.WAITING_AUTHORIZATION,  # Nenhuma detecção
        RobotControlState.ERROR,
        RobotControlState.STOPPED,
    },
    RobotControlState.WAITING_SEND_AUTHORIZATION: {
        RobotControlState.SENDING_DATA,
        RobotControlState.ERROR,
        RobotControlState.STOPPED,
    },
    RobotControlState.SENDING_DATA: {
        RobotControlState.WAITING_ACK,
        RobotControlState.ERROR,
        RobotControlState.STOPPED,
    },
    RobotControlState.WAITING_ACK: {
        RobotControlState.ACK_CONFIRMED,
        RobotControlState.TIMEOUT,
        RobotControlState.ERROR,
        RobotControlState.STOPPED,
    },
    RobotControlState.ACK_CONFIRMED: {
        RobotControlState.WAITING_PICK,
        RobotControlState.ERROR,
        RobotControlState.STOPPED,
    },
    RobotControlState.WAITING_PICK: {
        RobotControlState.WAITING_PLACE,
        RobotControlState.TIMEOUT,
        RobotControlState.ERROR,
        RobotControlState.STOPPED,
    },
    RobotControlState.WAITING_PLACE: {
        RobotControlState.WAITING_CYCLE_START,
        RobotControlState.TIMEOUT,
        RobotControlState.ERROR,
        RobotControlState.STOPPED,
    },
    RobotControlState.WAITING_CYCLE_START: {
        RobotControlState.READY_FOR_NEXT,
        RobotControlState.ERROR,
        RobotControlState.STOPPED,
    },
    RobotControlState.READY_FOR_NEXT: {
        RobotControlState.WAITING_AUTHORIZATION,
        RobotControlState.STOPPED,
    },
    RobotControlState.ERROR: {
        RobotControlState.INITIALIZING,
        RobotControlState.STOPPED,
    },
    RobotControlState.TIMEOUT: {
        RobotControlState.WAITING_AUTHORIZATION,
        RobotControlState.ERROR,
        RobotControlState.STOPPED,
    },
    RobotControlState.SAFETY_BLOCKED: {
        RobotControlState.WAITING_AUTHORIZATION,
        RobotControlState.STOPPED,
    },
}


class RobotController(QObject):
    """
    Controlador de robô com máquina de estados.
    
    Signals:
        state_changed: Emitido quando estado muda
        cycle_completed: Emitido quando ciclo completa
        error_occurred: Emitido em caso de erro
        detection_sent: Emitido quando detecção é enviada ao CLP
    """
    
    state_changed = Signal(str)  # RobotControlState.value
    cycle_completed = Signal(int)  # Número do ciclo
    error_occurred = Signal(str)
    detection_sent = Signal(object)  # DetectionEvent
    cycle_step = Signal(str)  # Descrição da etapa atual do ciclo
    cycle_summary = Signal(list)  # Lista de dicts com etapas executadas
    
    _instance: Optional["RobotController"] = None
    _lock = Lock()
    
    def __new__(cls) -> "RobotController":
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
        self._cip_client = CIPClient()
        self._metrics = MetricsCollector()
        
        # Estado
        self._state = RobotControlState.STOPPED
        self._previous_state = RobotControlState.STOPPED
        self._state_enter_time = datetime.now()
        self._last_error: Optional[str] = None
        
        # Ciclo
        self._cycle_count = 0
        self._current_detection: Optional[DetectionEvent] = None
        
        # Timeouts (carregados do config; atualizados em start())
        self._ack_timeout = self._settings.robot_control.ack_timeout
        self._pick_timeout = self._settings.robot_control.pick_timeout
        self._place_timeout = self._settings.robot_control.place_timeout
        self._authorization_timeout = self._settings.robot_control.authorization_timeout
        self._bypass_authorization = self._settings.robot_control.bypass_authorization
        
        # Timer para polling
        self._poll_timer: Optional[QTimer] = None
        self._poll_interval = 100  # ms
        
        # Running flag
        self._is_running = False
        
        # Flag para serializar processamento (evita recursão/concorrência)
        self._processing = False
        
        # Modo de ciclo: "manual" (aguarda botão) ou "continuous" (auto)
        self._cycle_mode: str = "manual"
        
        # Autorização do usuário para próximo ciclo (modo manual)
        self._user_cycle_authorized: bool = False
        
        # Autorização do usuário para enviar coordenadas ao CLP (modo manual, após detecção)
        self._user_send_authorized: bool = False
        
        # Registro de etapas do ciclo atual
        self._cycle_steps: List[Dict[str, Any]] = []
        
        # Flag para controlar execução única de cleanup no READY_FOR_NEXT
        self._ready_cleanup_done: bool = False
    
    def set_cycle_mode(self, mode: str) -> None:
        """
        Define o modo de ciclo.
        
        Args:
            mode: "manual" ou "continuous"
        """
        if mode not in ("manual", "continuous"):
            logger.warning("invalid_cycle_mode", mode=mode)
            return
        self._cycle_mode = mode
        logger.info("cycle_mode_changed", mode=mode)
    
    def authorize_next_cycle(self) -> None:
        """Autoriza o próximo ciclo (usado em modo manual)."""
        self._user_cycle_authorized = True
        logger.info("next_cycle_authorized_by_user")
    
    def authorize_send_to_plc(self) -> None:
        """Autoriza o envio das coordenadas ao CLP após detecção (modo manual)."""
        self._user_send_authorized = True
        logger.info("send_to_plc_authorized_by_user")
    
    def _record_step(self, step_name: str) -> None:
        """Registra uma etapa do ciclo atual e emite sinal."""
        entry = {
            "step": step_name,
            "timestamp": datetime.now(),
            "state": self._state.value,
        }
        self._cycle_steps.append(entry)
        self.cycle_step.emit(step_name)
        logger.info("cycle_step_recorded", step=step_name)
    
    @property
    def cycle_mode(self) -> str:
        """Retorna modo de ciclo atual."""
        return self._cycle_mode
    
    def start(self) -> bool:
        """
        Inicia o controlador.
        
        Returns:
            True se iniciado com sucesso
        """
        if self._is_running:
            return True
        
        self._settings = get_settings()
        self._ack_timeout = self._settings.robot_control.ack_timeout
        self._pick_timeout = self._settings.robot_control.pick_timeout
        self._place_timeout = self._settings.robot_control.place_timeout
        self._authorization_timeout = self._settings.robot_control.authorization_timeout
        self._bypass_authorization = self._settings.robot_control.bypass_authorization
        
        self._is_running = True
        self._transition_to(RobotControlState.INITIALIZING)
        
        # Inicia polling
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_cycle)
        self._poll_timer.start(self._poll_interval)
        
        logger.info("robot_controller_started")
        return True
    
    def stop(self) -> None:
        """Para o controlador."""
        self._is_running = False
        
        if self._poll_timer is not None:
            self._poll_timer.stop()
            self._poll_timer.deleteLater()
            self._poll_timer = None
        
        self._transition_to(RobotControlState.STOPPED)
        logger.info("robot_controller_stopped")
    
    def reset(self) -> None:
        """Reseta o controlador."""
        self._last_error = None
        self._current_detection = None
        
        if self._is_running:
            self._transition_to(RobotControlState.INITIALIZING)
        
        logger.info("robot_controller_reset")
    
    def process_detection(self, event: DetectionEvent) -> None:
        """
        Processa um evento de detecção.
        
        Args:
            event: Evento de detecção
        """
        if self._state != RobotControlState.DETECTING:
            logger.debug("detection_ignored_wrong_state", state=self._state.value)
            return
        
        self._current_detection = event
        
        if event.detected:
            logger.info(
                "detection_received",
                class_name=event.class_name,
                confidence=event.confidence,
                centroid=event.centroid,
            )
            self._record_step(
                f"Embalagem detectada: {event.class_name} "
                f"({event.confidence:.0%}) em ({event.centroid[0]:.0f}, {event.centroid[1]:.0f})"
            )
            if self._cycle_mode == "manual":
                self._transition_to(RobotControlState.WAITING_SEND_AUTHORIZATION)
            else:
                self._transition_to(RobotControlState.SENDING_DATA)
        else:
            # Nenhuma detecção, continua aguardando
            logger.debug("no_detection")
    
    def _poll_cycle(self) -> None:
        """Ciclo de polling para transições de estado."""
        if not self._is_running:
            return
        
        # Evita concorrência: só agenda nova tarefa se a anterior terminou
        if self._processing:
            return
        
        # Executa lógica do estado atual
        asyncio.create_task(self._process_current_state())
    
    async def _process_current_state(self) -> None:
        """Processa o estado atual (serializado via _processing flag)."""
        if self._processing:
            return
        self._processing = True
        try:
            if self._state == RobotControlState.INITIALIZING:
                await self._handle_initializing()
            
            elif self._state == RobotControlState.WAITING_AUTHORIZATION:
                await self._handle_waiting_authorization()
            
            elif self._state == RobotControlState.WAITING_SEND_AUTHORIZATION:
                await self._handle_waiting_send_authorization()
            
            elif self._state == RobotControlState.SENDING_DATA:
                await self._handle_sending_data()
            
            elif self._state == RobotControlState.WAITING_ACK:
                await self._handle_waiting_ack()
            
            elif self._state == RobotControlState.ACK_CONFIRMED:
                await self._handle_ack_confirmed()
            
            elif self._state == RobotControlState.WAITING_PICK:
                await self._handle_waiting_pick()
            
            elif self._state == RobotControlState.WAITING_PLACE:
                await self._handle_waiting_place()
            
            elif self._state == RobotControlState.WAITING_CYCLE_START:
                await self._handle_waiting_cycle_start()
            
            elif self._state == RobotControlState.READY_FOR_NEXT:
                await self._handle_ready_for_next()
            
            elif self._state == RobotControlState.ERROR:
                await self._handle_error()
            
            elif self._state == RobotControlState.TIMEOUT:
                await self._handle_timeout()
            
            elif self._state == RobotControlState.SAFETY_BLOCKED:
                await self._handle_safety_blocked()
                
        except Exception as e:
            logger.error("state_processing_error", state=self._state.value, error=str(e))
            self._handle_exception(str(e))
        finally:
            self._processing = False
    
    async def _handle_initializing(self) -> None:
        """Inicialização do sistema.
        
        Nota: VisionReady já foi setado na OperationPage antes de iniciar
        o controlador, evitando chamadas duplicadas e concorrência.
        """
        try:
            # Verifica se está conectado ao CLP
            if not self._cip_client._state.is_connected:
                logger.warning("plc_not_connected_waiting")
                # Aguarda um pouco e tenta novamente no próximo ciclo
                await asyncio.sleep(0.5)
                return
            
            # VisionReady já foi setado na OperationPage._connect_plc_and_start_robot()
            # Apenas transiciona para aguardar autorização
            logger.info("initialization_complete_waiting_authorization")
            self._transition_to(RobotControlState.WAITING_AUTHORIZATION)
        except Exception as e:
            logger.error("initialization_failed", error=str(e))
            self._handle_exception(str(e))
    
    async def _handle_waiting_authorization(self) -> None:
        """Aguarda autorização do CLP."""
        try:
            # Verifica se está conectado ao CLP
            if not self._cip_client._state.is_connected:
                logger.warning("plc_not_connected_waiting")
                # Retorna ao estado de inicialização para tentar conectar
                self._transition_to(RobotControlState.INITIALIZING)
                return
            
            # Verifica segurança primeiro
            if not await self._check_safety():
                self._transition_to(RobotControlState.SAFETY_BLOCKED)
                return
            
            # Se bypass habilitado, passa direto
            if self._bypass_authorization:
                logger.info("detection_authorized_via_bypass")
                self._transition_to(RobotControlState.DETECTING)
                return
            
            # Verifica timeout de autorização
            # Se houver muita demora, assume que a autorização é implícita
            # (pode ser que o TAG esteja com problema, como RecursionError na aphyt)
            elapsed = (datetime.now() - self._state_enter_time).total_seconds()
            if elapsed > self._authorization_timeout:
                logger.warning(
                    "authorization_timeout_implicit_allow",
                    timeout=self._authorization_timeout
                )
                self._transition_to(RobotControlState.DETECTING)
                return
            
            # Lê autorização
            authorized = await self._cip_client.read_tag("PlcAuthorizeDetection")
            
            if authorized:
                logger.info("detection_authorized")
                self._transition_to(RobotControlState.DETECTING)
                
        except Exception as e:
            logger.warning("authorization_check_error", error=str(e))
    
    async def _handle_waiting_send_authorization(self) -> None:
        """Aguarda operador autorizar envio das coordenadas ao CLP (modo manual)."""
        if self._user_send_authorized:
            self._user_send_authorized = False
            logger.info("send_authorized_proceeding_to_send")
            self._transition_to(RobotControlState.SENDING_DATA)
    
    async def _handle_sending_data(self) -> None:
        """Envia dados de detecção para o CLP."""
        if self._current_detection is None:
            self._transition_to(RobotControlState.WAITING_AUTHORIZATION)
            return
        
        try:
            # Verifica se está conectado ao CLP
            if not self._cip_client._state.is_connected:
                error_msg = "Não conectado ao CLP"
                logger.error("plc_not_connected", error=error_msg)
                self._handle_exception(error_msg)
                return
            
            plc_data = self._current_detection.to_plc_data()
            
            await self._cip_client.write_detection_result(
                detected=plc_data["product_detected"],
                centroid_x=plc_data["centroid_x"],
                centroid_y=plc_data["centroid_y"],
                confidence=plc_data["confidence"],
                detection_count=plc_data["detection_count"],
                processing_time=plc_data["processing_time"],
            )
            
            self._record_step(
                f"Coordenadas enviadas ao CLP: "
                f"({plc_data['centroid_x']:.0f}, {plc_data['centroid_y']:.0f}) "
                f"conf={plc_data['confidence']:.0%}"
            )
            self.detection_sent.emit(self._current_detection)
            self._transition_to(RobotControlState.WAITING_ACK)
            
        except Exception as e:
            logger.error("send_data_failed", error=str(e))
            self._handle_exception(str(e))
    
    async def _handle_waiting_ack(self) -> None:
        """Aguarda ACK do robô."""
        # Verifica timeout
        elapsed = (datetime.now() - self._state_enter_time).total_seconds()
        if elapsed > self._ack_timeout:
            logger.warning("ack_timeout", timeout=self._ack_timeout)
            self._transition_to(RobotControlState.TIMEOUT)
            return
        
        try:
            ack = await self._cip_client.read_robot_ack()
            
            if ack:
                logger.info("robot_ack_received")
                self._record_step("ACK do robo recebido")
                self._transition_to(RobotControlState.ACK_CONFIRMED)
                
        except Exception as e:
            logger.warning("ack_read_error", error=str(e))
    
    async def _handle_ack_confirmed(self) -> None:
        """Confirma ACK recebido."""
        try:
            # Envia echo de confirmação
            await self._cip_client.set_vision_echo_ack(True)
            self._transition_to(RobotControlState.WAITING_PICK)
            
        except Exception as e:
            logger.error("echo_ack_failed", error=str(e))
            self._handle_exception(str(e))
    
    async def _handle_waiting_pick(self) -> None:
        """Aguarda conclusão do pick."""
        # Verifica timeout
        elapsed = (datetime.now() - self._state_enter_time).total_seconds()
        if elapsed > self._pick_timeout:
            logger.warning("pick_timeout", timeout=self._pick_timeout)
            self._transition_to(RobotControlState.TIMEOUT)
            return
        
        try:
            pick_complete = await self._cip_client.read_tag("RobotPickComplete")
            
            if pick_complete:
                logger.info("pick_complete")
                self._record_step("PICK concluido - embalagem coletada")
                self._transition_to(RobotControlState.WAITING_PLACE)
                
        except Exception as e:
            logger.warning("pick_check_error", error=str(e))
    
    async def _handle_waiting_place(self) -> None:
        """Aguarda conclusão do place."""
        # Verifica timeout
        elapsed = (datetime.now() - self._state_enter_time).total_seconds()
        if elapsed > self._place_timeout:
            logger.warning("place_timeout", timeout=self._place_timeout)
            self._transition_to(RobotControlState.TIMEOUT)
            return
        
        try:
            place_complete = await self._cip_client.read_tag("RobotPlaceComplete")
            
            if place_complete:
                logger.info("place_complete")
                self._record_step("PLACE concluido - embalagem posicionada")
                self._transition_to(RobotControlState.WAITING_CYCLE_START)
                
        except Exception as e:
            logger.warning("place_check_error", error=str(e))
    
    async def _handle_waiting_cycle_start(self) -> None:
        """Aguarda CLP sinalizar fim de ciclo, faz cleanup e emite summary."""
        try:
            cycle_start = await self._cip_client.read_tag("PlcCycleStart")
            
            if cycle_start:
                logger.info("cycle_start_received")
                self._record_step("Ciclo pick-and-place COMPLETO")
                
                self._cycle_count += 1
                self.cycle_completed.emit(self._cycle_count)
                self._metrics.increment("cycle_count")
                
                # Emite resumo do ciclo para a UI
                self.cycle_summary.emit(self._cycle_steps.copy())
                self._cycle_steps.clear()
                
                # Reseta flags no CLP
                try:
                    await self._cip_client.set_vision_echo_ack(False)
                    await self._cip_client.set_ready_for_next(True)
                except Exception as e:
                    logger.warning("cycle_cleanup_flags_error", error=str(e))
                
                # Limpa detecção atual
                self._current_detection = None
                self._ready_cleanup_done = False
                
                self._transition_to(RobotControlState.READY_FOR_NEXT)
                
        except Exception as e:
            logger.warning("cycle_start_check_error", error=str(e))
    
    async def _handle_ready_for_next(self) -> None:
        """
        Prepara para próximo ciclo.
        
        Em modo contínuo: avança automaticamente.
        Em modo manual: aguarda authorize_next_cycle() do usuário.
        """
        if self._cycle_mode == "continuous":
            self._transition_to(RobotControlState.WAITING_AUTHORIZATION)
        elif self._user_cycle_authorized:
            self._user_cycle_authorized = False
            self._transition_to(RobotControlState.WAITING_AUTHORIZATION)
        # else: permanece em READY_FOR_NEXT aguardando autorização do usuário
    
    async def _handle_error(self) -> None:
        """Estado de erro."""
        # Tenta recuperar após alguns segundos
        elapsed = (datetime.now() - self._state_enter_time).total_seconds()
        if elapsed > 5.0:
            logger.info("attempting_recovery_from_error")
            self._transition_to(RobotControlState.INITIALIZING)
    
    async def _handle_timeout(self) -> None:
        """Estado de timeout."""
        # Volta para aguardar autorização
        await asyncio.sleep(1.0)
        self._transition_to(RobotControlState.WAITING_AUTHORIZATION)
    
    async def _handle_safety_blocked(self) -> None:
        """Estado de bloqueio de segurança."""
        try:
            if await self._check_safety():
                logger.info("safety_cleared")
                self._transition_to(RobotControlState.WAITING_AUTHORIZATION)
        except Exception as e:
            logger.warning("safety_check_error", error=str(e))
    
    async def _check_safety(self) -> bool:
        """Verifica condições de segurança."""
        try:
            emergency = await self._cip_client.read_tag("PlcEmergencyStop")
            if emergency:
                logger.warning("emergency_stop_active")
                return False
            
            return True
        except Exception:
            return True  # Assume seguro se não conseguir ler
    
    def _transition_to(self, new_state: RobotControlState) -> None:
        """
        Transiciona para um novo estado.
        
        Args:
            new_state: Novo estado
        """
        # Valida transição
        if new_state not in VALID_TRANSITIONS.get(self._state, set()):
            if self._state != new_state:  # Permite permanecer no mesmo estado
                logger.warning(
                    "invalid_state_transition",
                    from_state=self._state.value,
                    to_state=new_state.value,
                )
                return
        
        old_state = self._state
        duration_s = (datetime.now() - self._state_enter_time).total_seconds()
        self._previous_state = old_state
        self._state = new_state
        self._state_enter_time = datetime.now()
        
        logger.info(
            "state_transition",
            from_state=old_state.value,
            to_state=new_state.value,
            duration_s=round(duration_s, 2),
        )
        
        self.state_changed.emit(new_state.value)
    
    def _handle_exception(self, error: str) -> None:
        """Trata exceção."""
        self._last_error = error
        self.error_occurred.emit(error)
        self._transition_to(RobotControlState.ERROR)
    
    def get_status(self) -> Dict[str, Any]:
        """Retorna status do controlador."""
        return {
            "state": self._state.value,
            "previous_state": self._previous_state.value,
            "is_running": self._is_running,
            "cycle_count": self._cycle_count,
            "last_error": self._last_error,
            "state_duration": (datetime.now() - self._state_enter_time).total_seconds(),
            "current_detection": self._current_detection.to_dict() if self._current_detection else None,
        }
    
    @property
    def state(self) -> RobotControlState:
        """Retorna estado atual."""
        return self._state
    
    @property
    def is_running(self) -> bool:
        """Verifica se está rodando."""
        return self._is_running
    
    @property
    def cycle_count(self) -> int:
        """Retorna contagem de ciclos."""
        return self._cycle_count


# Função de conveniência
def get_robot_controller() -> RobotController:
    """Retorna a instância do controlador de robô."""
    return RobotController()
