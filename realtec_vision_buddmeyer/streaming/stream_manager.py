# -*- coding: utf-8 -*-
"""
Gerenciador principal de streaming de vídeo.
"""

import time
from pathlib import Path
from threading import Lock
from typing import Optional, Dict, Any

import numpy as np
from PySide6.QtCore import QObject, Signal, QThread, QMutex, QWaitCondition

from config import get_settings
from core.logger import get_logger
from core.metrics import MetricsCollector
from core.exceptions import StreamError

from .source_adapters import BaseSourceAdapter, SourceType, create_adapter, GenTLHarvesterAdapter
from .frame_buffer import FrameBuffer, FrameInfo
from .stream_health import StreamHealth, HealthStatus

logger = get_logger("streaming.manager")


class StreamWorker(QThread):
    """
    Thread de captura de frames.
    
    Signals:
        frame_captured: Emitido quando um frame é capturado
        error_occurred: Emitido em caso de erro
    """
    
    frame_captured = Signal(object)  # FrameInfo
    error_occurred = Signal(str)
    
    def __init__(self, adapter: BaseSourceAdapter, target_fps: float = 30.0):
        super().__init__()
        
        self._adapter = adapter
        self._target_fps = target_fps
        self._running = False
        self._paused = False
        self._mutex = QMutex()
        self._pause_condition = QWaitCondition()
    
    def run(self) -> None:
        """Loop principal de captura. Abre e fecha o adaptador nesta thread (SDK GenTL)."""
        try:
            self._adapter.open()
        except Exception as e:
            logger.error("stream_adapter_open_failed", error=str(e))
            self.error_occurred.emit(str(e))
            return

        self._running = True
        frame_interval = 1.0 / self._target_fps if self._target_fps > 0 else 0.033
        
        logger.info("stream_worker_started", target_fps=self._target_fps)
        
        try:
            while self._running:
                # Verifica pause
                self._mutex.lock()
                while self._paused and self._running:
                    self._pause_condition.wait(self._mutex)
                self._mutex.unlock()
                
                if not self._running:
                    break
                
                start_time = time.perf_counter()
                
                try:
                    frame_info = self._adapter.read()
                    
                    if frame_info is not None:
                        self.frame_captured.emit(frame_info)
                    else:
                        logger.warning("stream_read_none")
                        time.sleep(0.1)
                        continue
                        
                except Exception as e:
                    logger.error("stream_read_error", error=str(e))
                    self.error_occurred.emit(str(e))
                    time.sleep(0.5)
                    continue
                
                # Controle de FPS
                elapsed = time.perf_counter() - start_time
                sleep_time = frame_interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
        finally:
            try:
                self._adapter.close()
            except Exception as e:
                logger.warning("stream_adapter_close_failed", error=str(e))
            logger.info("stream_worker_stopped")
    
    def pause(self) -> None:
        """Pausa a captura."""
        self._mutex.lock()
        self._paused = True
        self._mutex.unlock()
    
    def resume(self) -> None:
        """Retoma a captura."""
        self._mutex.lock()
        self._paused = False
        self._pause_condition.wakeAll()
        self._mutex.unlock()
    
    def stop(self, timeout_ms: int = 8000) -> None:
        """Para a captura e aguarda a thread fechar o adaptador."""
        self._running = False
        if hasattr(self._adapter, "request_stop"):
            self._adapter.request_stop()
        self._mutex.lock()
        self._paused = False
        self._pause_condition.wakeAll()
        self._mutex.unlock()
        if not self.wait(timeout_ms):
            logger.warning("stream_worker_stop_timeout", timeout_ms=timeout_ms)


class StreamManager(QObject):
    """
    Gerenciador central de streaming de vídeo.
    
    Singleton que gerencia:
    - Adaptador de fonte de vídeo
    - Thread de captura
    - Buffer de frames
    - Health check
    
    Signals:
        frame_available: Emitido quando um novo frame está disponível
        stream_started: Emitido quando o stream inicia
        stream_stopped: Emitido quando o stream para
        stream_error: Emitido em caso de erro
        health_changed: Emitido quando status de saúde muda
    """
    
    frame_available = Signal(np.ndarray)
    frame_info_available = Signal(object)  # FrameInfo
    stream_started = Signal()
    stream_stopped = Signal()
    stream_error = Signal(str)
    health_changed = Signal(object)  # StreamHealthInfo
    
    _instance: Optional["StreamManager"] = None
    _lock = Lock()
    
    def __new__(cls) -> "StreamManager":
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
        self._adapter: Optional[BaseSourceAdapter] = None
        self._worker: Optional[StreamWorker] = None
        self._buffer: FrameBuffer = FrameBuffer(
            max_size=self._settings.streaming.max_frame_buffer_size
        )
        self._health = StreamHealth()
        self._metrics = MetricsCollector()
        
        self._is_running = False
        self._current_frame: Optional[FrameInfo] = None
        
        # Conecta sinais de health
        self._health.health_changed.connect(self.health_changed.emit)
    
    def start(self) -> bool:
        """
        Inicia o streaming usando as configurações atuais em memória.
        
        IMPORTANTE: NÃO recarrega do arquivo config.yaml.
        As configurações devem ser atualizadas ANTES via change_source()
        ou diretamente no objeto settings. Isso garante que a fonte
        selecionada na UI (USB, video, RTSP, GigE) seja respeitada.
        
        Returns:
            True se iniciado com sucesso
        """
        if self._is_running:
            logger.warning("stream_already_running")
            return True
        
        return self._start_with_current_settings()
    
    def stop(self) -> None:
        """Para o streaming e libera a fonte, mesmo se o start ficou a meio."""
        worker = self._worker
        adapter = self._adapter
        self._worker = None

        if worker is not None:
            worker.stop()
            worker.deleteLater()

        # Se a thread não fechou o adaptador (timeout ou start parcial), fecha aqui.
        if adapter is not None and getattr(adapter, "is_open", False):
            try:
                adapter.close()
            except Exception as e:
                logger.warning("adapter_close_after_stop_failed", error=str(e))
        self._adapter = None

        self._buffer.clear()
        was_running = self._is_running
        self._is_running = False
        self._current_frame = None

        logger.info("stream_stopped")
        if was_running:
            self.stream_stopped.emit()
    
    def get_gentl_adapter(self) -> Optional[Any]:
        """
        Retorna o adaptador GenTL atual, se o stream estiver rodando com fonte GenTL.
        Usado pela UI para abrir a tela de ajustes da câmera (gain, exposure, etc.).
        """
        if not self._is_running or self._adapter is None:
            return None
        if isinstance(self._adapter, GenTLHarvesterAdapter):
            return self._adapter
        return None

    def pause(self) -> None:
        """Pausa o streaming."""
        if self._worker is not None:
            self._worker.pause()
            logger.info("stream_paused")
    
    def resume(self) -> None:
        """Retoma o streaming."""
        if self._worker is not None:
            self._worker.resume()
            logger.info("stream_resumed")
    
    def change_source(
        self,
        source_type: str,
        video_path: str = "",
        camera_index: int = 0,
        rtsp_url: str = "",
        gige_ip: str = "",
        gige_port: int = 3956,
        gentl_cti_path: str = "",
        gentl_device_index: int = 0,
        loop_video: bool = True,
        **kwargs
    ) -> bool:
        """
        Muda a fonte de vídeo.
        
        Args:
            source_type: Tipo de fonte
            video_path: Caminho do vídeo
            camera_index: Índice da câmera
            rtsp_url: URL RTSP
            gige_ip: IP GigE
            gige_port: Porta GigE
            gentl_cti_path: Caminho do CTI GenTL (Harvester)
            gentl_device_index: Índice da câmera GenTL
            loop_video: Loop do vídeo
        
        Returns:
            True se mudou com sucesso
        """
        was_running = self._is_running
        
        # Para stream atual apenas se estava rodando
        if was_running:
            # Para worker e fecha adaptador atual
            if self._worker is not None:
                self._worker.stop()
                self._worker.deleteLater()
                self._worker = None
            
            if self._adapter is not None and getattr(self._adapter, "is_open", False):
                try:
                    self._adapter.close()
                except Exception:
                    pass
            self._adapter = None
            
            self._is_running = False
        
        # Usa as configurações atuais (NÃO recarrega do arquivo para não perder mudanças)
        # self._settings = get_settings()  # Removido para preservar mudanças em memória
        
        # Atualiza configuração em memória
        settings = self._settings.streaming
        settings.source_type = source_type
        
        if video_path:
            settings.video_path = video_path
        if camera_index >= 0:
            settings.usb_camera_index = camera_index
        if rtsp_url:
            settings.rtsp_url = rtsp_url
        if gige_ip:
            settings.gige_ip = gige_ip
        if gige_port > 0:
            settings.gige_port = gige_port
        if gentl_cti_path:
            settings.gentl_cti_path = gentl_cti_path
        if gentl_device_index >= 0:
            settings.gentl_device_index = gentl_device_index
        if loop_video is not None:
            settings.loop_video = loop_video
        
        logger.info(
            "source_changed",
            source_type=source_type,
            video_path=video_path if video_path else None,
        )
        
        # Reinicia se estava rodando
        if was_running:
            success = self._start_with_current_settings()
            if not success:
                # Informa a UI que o stream parou por falha no restart
                logger.error(
                    "change_source_restart_failed",
                    source_type=source_type,
                )
                self.stream_stopped.emit()
            return success
        
        return True
    
    def _start_with_current_settings(self) -> bool:
        """
        Inicia stream usando as configurações atuais em memória.
        
        Usa o source_type e parâmetros que já estão no objeto settings
        (definidos via change_source() ou diretamente pela UI).
        NÃO recarrega do arquivo config.yaml.
        
        Returns:
            True se iniciado com sucesso
        """
        if self._is_running:
            logger.warning("stream_already_running")
            return True
        
        try:
            settings = self._settings.streaming
            
            # Log detalhado do que será usado — essencial para diagnóstico
            logger.info(
                "stream_starting_with_settings",
                source_type=settings.source_type,
                video_path=settings.video_path if settings.source_type == "video" else None,
                usb_camera_index=settings.usb_camera_index if settings.source_type == "usb" else None,
                rtsp_url=settings.rtsp_url if settings.source_type == "rtsp" else None,
                gige_ip=settings.gige_ip if settings.source_type == "gige" else None,
                gentl_cti_path=settings.gentl_cti_path if settings.source_type == "gentl" else None,
            )
            
            # Validações específicas por tipo de fonte
            if settings.source_type == "video":
                video_path_str = settings.video_path
                video_path_obj = Path(video_path_str)
                
                # Tenta resolver caminho relativo
                if not video_path_obj.is_absolute():
                    base_path = Path(__file__).parent.parent
                    video_path_obj = base_path / video_path_str
                
                # Normaliza caminho (resolve .., ./, etc)
                try:
                    video_path_obj = video_path_obj.resolve()
                except Exception:
                    pass
                
                if not video_path_obj.exists():
                    error_msg = f"Arquivo de vídeo não encontrado: {video_path_obj}"
                    logger.error("video_file_not_found", path=str(video_path_obj))
                    self.stream_error.emit(error_msg)
                    return False
                
                # Atualiza configuração com caminho normalizado
                settings.video_path = str(video_path_obj)
                logger.info("using_video_path", path=str(video_path_obj))
            
            elif settings.source_type == "usb":
                logger.info(
                    "using_usb_camera",
                    camera_index=settings.usb_camera_index,
                )
            
            elif settings.source_type == "rtsp":
                if not settings.rtsp_url:
                    error_msg = "URL RTSP não configurada"
                    logger.error("rtsp_url_empty")
                    self.stream_error.emit(error_msg)
                    return False
                logger.info("using_rtsp_stream", url=settings.rtsp_url)
            
            elif settings.source_type == "gige":
                if not settings.gige_ip:
                    error_msg = "IP da câmera GigE não configurado"
                    logger.error("gige_ip_empty")
                    self.stream_error.emit(error_msg)
                    return False
                logger.info(
                    "using_gige_camera",
                    ip=settings.gige_ip,
                    port=settings.gige_port,
                )
            
            elif settings.source_type == "gentl":
                cti_path = Path(settings.gentl_cti_path)
                if not settings.gentl_cti_path or not cti_path.exists():
                    error_msg = "Caminho do arquivo CTI GenTL não configurado ou não encontrado"
                    logger.error("gentl_cti_empty_or_not_found", path=settings.gentl_cti_path)
                    self.stream_error.emit(error_msg)
                    return False
                logger.info(
                    "using_gentl_camera",
                    cti_path=settings.gentl_cti_path,
                    device_index=settings.gentl_device_index,
                )
            
            # Cria adaptador de acordo com o source_type
            self._adapter = create_adapter(
                source_type=settings.source_type,
                video_path=settings.video_path,
                camera_index=settings.usb_camera_index,
                rtsp_url=settings.rtsp_url,
                gige_ip=settings.gige_ip,
                gige_port=settings.gige_port,
                gentl_cti_path=settings.gentl_cti_path,
                gentl_device_index=settings.gentl_device_index,
                gentl_max_dimension=settings.gentl_max_dimension,
                gentl_target_fps=settings.gentl_target_fps,
                loop_video=settings.loop_video,
            )
            
            # Abre a fonte na thread de captura (open/read/close no mesmo thread do SDK).
            target_fps = 30.0
            if settings.source_type == "gentl" and settings.gentl_target_fps > 0:
                target_fps = float(settings.gentl_target_fps)
            
            self._worker = StreamWorker(self._adapter, target_fps)
            self._worker.frame_captured.connect(self._on_frame_captured)
            self._worker.error_occurred.connect(self._on_error)
            
            self._worker.start()
            self._is_running = True
            self._health.reset()
            
            logger.info(
                "stream_started",
                source_type=settings.source_type,
                target_fps=target_fps,
            )
            
            self.stream_started.emit()
            return True
            
        except Exception as e:
            logger.error("stream_start_failed", error=str(e), source_type=self._settings.streaming.source_type)
            self.stop()
            self.stream_error.emit(str(e))
            return False
    
    def get_current_frame(self) -> Optional[np.ndarray]:
        """
        Retorna o frame atual.
        
        Returns:
            Frame numpy ou None
        """
        if self._current_frame is not None:
            return self._current_frame.frame.copy()
        return None
    
    def get_current_frame_info(self) -> Optional[FrameInfo]:
        """Retorna informações do frame atual."""
        return self._current_frame
    
    def get_fps(self) -> float:
        """Retorna FPS atual."""
        return self._health.current_fps
    
    def get_status(self) -> Dict[str, Any]:
        """
        Retorna status do stream.
        
        Returns:
            Dict com status completo
        """
        health = self._health.check_health()
        
        return {
            "running": self._is_running,
            "source_type": self._settings.streaming.source_type,
            "fps": self._health.current_fps,
            "frame_count": self._health.frame_count,
            "drop_count": self._health.drop_count,
            "buffer_size": self._buffer.size,
            "buffer_usage": self._buffer.usage_percent,
            "health": health.to_dict(),
        }
    
    @property
    def is_running(self) -> bool:
        """Verifica se está rodando."""
        return self._is_running
    
    def _on_frame_captured(self, frame_info: FrameInfo) -> None:
        """Handler para frame capturado."""
        # Atualiza frame atual
        self._current_frame = frame_info
        
        # Adiciona ao buffer
        self._buffer.put(frame_info)
        
        # Atualiza health
        self._health.record_frame()
        self._health.set_buffer_usage(self._buffer.usage_percent)
        
        # Métricas
        self._metrics.record("stream_fps", self._health.current_fps)
        
        # Emite sinais
        self.frame_available.emit(frame_info.frame)
        self.frame_info_available.emit(frame_info)
    
    def _on_error(self, error: str) -> None:
        """Handler para erro."""
        logger.error("stream_error", error=error)
        self._health.record_drop()
        self.stream_error.emit(error)
        worker = self._worker
        if worker is not None and not worker.isRunning():
            self._is_running = False
            self._adapter = None
            self._worker = None
            self.stream_stopped.emit()


# Função de conveniência
def get_stream_manager() -> StreamManager:
    """Retorna a instância do gerenciador de stream."""
    return StreamManager()
