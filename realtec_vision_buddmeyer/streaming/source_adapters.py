# -*- coding: utf-8 -*-
"""
Adaptadores de fonte de vídeo para diferentes tipos de entrada.
"""

from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any
import gc
import platform
import time

import cv2
import numpy as np

from core.logger import get_logger
from core.exceptions import StreamSourceError
from .frame_buffer import FrameInfo

logger = get_logger("streaming.adapters")


class SourceType(str, Enum):
    """Tipos de fonte de vídeo suportados."""
    
    VIDEO = "video"   # Arquivo MP4, AVI, MOV
    USB = "usb"       # Câmera USB/USB-C
    RTSP = "rtsp"     # Stream RTSP
    GIGE = "gige"     # Câmera GigE (Gigabit Ethernet)
    GENTL = "gentl"   # Câmera GenTL (Harvester, ex.: Omron Sentech)


class BaseSourceAdapter(ABC):
    """
    Interface base para adaptadores de fonte de vídeo.
    """
    
    def __init__(self, source_type: SourceType):
        self.source_type = source_type
        self._capture: Optional[cv2.VideoCapture] = None
        self._is_open = False
        self._frame_count = 0
        self._start_time: Optional[float] = None
        self._stop_requested = False
    
    @abstractmethod
    def open(self) -> bool:
        """
        Abre a fonte de vídeo.
        
        Returns:
            True se aberto com sucesso
        """
        pass
    
    @abstractmethod
    def read(self) -> Optional[FrameInfo]:
        """
        Lê um frame da fonte.
        
        Returns:
            FrameInfo ou None se falhar
        """
        pass
    
    def request_stop(self) -> None:
        """Sinaliza para a thread de captura interromper o próximo read()."""
        self._stop_requested = True

    def close(self) -> None:
        """Fecha a fonte de vídeo."""
        self._stop_requested = True
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        self._is_open = False
        logger.info("source_closed", source_type=self.source_type.value)
    
    def get_properties(self) -> Dict[str, Any]:
        """Retorna propriedades da fonte."""
        if self._capture is None:
            return {}
        
        return {
            "width": int(self._capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(self._capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "fps": self._capture.get(cv2.CAP_PROP_FPS),
            "frame_count": int(self._capture.get(cv2.CAP_PROP_FRAME_COUNT)),
            "fourcc": int(self._capture.get(cv2.CAP_PROP_FOURCC)),
        }
    
    def get_fps(self) -> float:
        """Retorna FPS real de captura."""
        if self._start_time is None or self._frame_count == 0:
            return 0.0
        
        elapsed = time.time() - self._start_time
        return self._frame_count / elapsed if elapsed > 0 else 0.0
    
    @property
    def is_open(self) -> bool:
        """Verifica se a fonte está aberta."""
        return self._is_open
    
    def _create_frame_info(self, frame: np.ndarray) -> FrameInfo:
        """Cria FrameInfo a partir de um frame."""
        self._frame_count += 1
        return FrameInfo.from_frame(
            frame=frame,
            frame_id=self._frame_count,
            source_type=self.source_type.value,
        )


class VideoFileAdapter(BaseSourceAdapter):
    """
    Adaptador para arquivos de vídeo (MP4, AVI, MOV).
    
    Suporta loop de vídeo.
    """
    
    def __init__(self, video_path: str, loop: bool = True):
        """
        Inicializa o adaptador.
        
        Args:
            video_path: Caminho para o arquivo de vídeo
            loop: Se True, reinicia o vídeo ao terminar
        """
        super().__init__(SourceType.VIDEO)
        self.video_path = Path(video_path)
        self.loop = loop
        self._total_frames = 0
    
    def open(self) -> bool:
        """Abre o arquivo de vídeo."""
        if not self.video_path.exists():
            logger.error("video_not_found", path=str(self.video_path))
            raise StreamSourceError(
                f"Arquivo de vídeo não encontrado: {self.video_path}",
                {"path": str(self.video_path)}
            )
        
        self._capture = cv2.VideoCapture(str(self.video_path))
        
        if not self._capture.isOpened():
            logger.error("video_open_failed", path=str(self.video_path))
            raise StreamSourceError(
                f"Não foi possível abrir o vídeo: {self.video_path}",
                {"path": str(self.video_path)}
            )
        
        self._is_open = True
        self._start_time = time.time()
        self._total_frames = int(self._capture.get(cv2.CAP_PROP_FRAME_COUNT))
        
        props = self.get_properties()
        logger.info(
            "video_opened",
            path=str(self.video_path),
            width=props["width"],
            height=props["height"],
            fps=props["fps"],
            total_frames=self._total_frames,
        )
        
        return True
    
    def read(self) -> Optional[FrameInfo]:
        """Lê um frame do vídeo."""
        if not self._is_open or self._capture is None:
            return None
        
        ret, frame = self._capture.read()
        
        if not ret:
            if self.loop:
                # Reinicia o vídeo
                self._capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self._capture.read()
                if not ret:
                    return None
                logger.debug("video_looped", path=str(self.video_path))
            else:
                logger.info("video_ended", path=str(self.video_path))
                return None
        
        return self._create_frame_info(frame)
    
    def seek(self, frame_number: int) -> bool:
        """
        Pula para um frame específico.
        
        Args:
            frame_number: Número do frame
        
        Returns:
            True se bem sucedido
        """
        if not self._is_open or self._capture is None:
            return False
        
        self._capture.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
        return True
    
    @property
    def current_position(self) -> int:
        """Retorna posição atual no vídeo."""
        if self._capture is None:
            return 0
        return int(self._capture.get(cv2.CAP_PROP_POS_FRAMES))
    
    @property
    def total_frames(self) -> int:
        """Retorna total de frames do vídeo."""
        return self._total_frames


class USBCameraAdapter(BaseSourceAdapter):
    """
    Adaptador para câmeras USB/USB-C.
    """
    
    def __init__(self, camera_index: int = 0, width: int = 640, height: int = 480):
        """
        Inicializa o adaptador.
        
        Args:
            camera_index: Índice da câmera USB
            width: Largura desejada
            height: Altura desejada
        """
        super().__init__(SourceType.USB)
        self.camera_index = camera_index
        self.width = width
        self.height = height
    
    def open(self) -> bool:
        """Abre a câmera USB."""
        # DirectShow (CAP_DSHOW) só existe no Windows; Linux/macOS usam V4L2/AVFoundation
        if platform.system() == "Windows":
            self._capture = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        else:
            self._capture = cv2.VideoCapture(self.camera_index)
        
        if not self._capture.isOpened():
            # Fallback para backend padrão (ex.: V4L2 no Linux)
            self._capture = cv2.VideoCapture(self.camera_index)
        
        if not self._capture.isOpened():
            logger.error("usb_camera_open_failed", index=self.camera_index)
            raise StreamSourceError(
                f"Não foi possível abrir a câmera USB: {self.camera_index}",
                {"camera_index": self.camera_index}
            )
        
        # Configura resolução
        self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        
        self._is_open = True
        self._start_time = time.time()
        
        props = self.get_properties()
        logger.info(
            "usb_camera_opened",
            index=self.camera_index,
            width=props["width"],
            height=props["height"],
        )
        
        return True
    
    def read(self) -> Optional[FrameInfo]:
        """Lê um frame da câmera."""
        if not self._is_open or self._capture is None:
            return None
        
        ret, frame = self._capture.read()
        
        if not ret:
            logger.warning("usb_camera_read_failed", index=self.camera_index)
            return None
        
        return self._create_frame_info(frame)


class RTSPAdapter(BaseSourceAdapter):
    """
    Adaptador para streams RTSP.
    """
    
    def __init__(self, url: str, buffer_size: int = 1):
        """
        Inicializa o adaptador.
        
        Args:
            url: URL do stream RTSP
            buffer_size: Tamanho do buffer (1 = mínimo para menor latência)
        """
        super().__init__(SourceType.RTSP)
        self.url = url
        self.buffer_size = buffer_size
    
    def open(self) -> bool:
        """Abre o stream RTSP."""
        # Configurações para menor latência
        self._capture = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
        
        if not self._capture.isOpened():
            logger.error("rtsp_open_failed", url=self.url)
            raise StreamSourceError(
                f"Não foi possível abrir stream RTSP: {self.url}",
                {"url": self.url}
            )
        
        # Buffer mínimo para menor latência
        self._capture.set(cv2.CAP_PROP_BUFFERSIZE, self.buffer_size)
        
        self._is_open = True
        self._start_time = time.time()
        
        props = self.get_properties()
        logger.info(
            "rtsp_opened",
            url=self.url,
            width=props.get("width"),
            height=props.get("height"),
        )
        
        return True
    
    def read(self) -> Optional[FrameInfo]:
        """Lê um frame do stream."""
        if not self._is_open or self._capture is None:
            return None
        
        ret, frame = self._capture.read()
        
        if not ret:
            logger.warning("rtsp_read_failed", url=self.url)
            return None
        
        return self._create_frame_info(frame)


class GigECameraAdapter(BaseSourceAdapter):
    """
    Adaptador para câmeras GigE Vision.
    
    Nota: Requer drivers GigE instalados.
    """
    
    def __init__(self, ip: str, port: int = 3956):
        """
        Inicializa o adaptador.
        
        Args:
            ip: Endereço IP da câmera
            port: Porta GigE (padrão: 3956)
        """
        super().__init__(SourceType.GIGE)
        self.ip = ip
        self.port = port
    
    def open(self) -> bool:
        """Abre a câmera GigE."""
        # Formato de URL para câmeras GigE
        gige_url = f"gige://{self.ip}:{self.port}"
        
        # Tenta abrir via GStreamer
        gst_pipeline = (
            f"udpsrc address={self.ip} port={self.port} ! "
            "application/x-rtp,encoding-name=JPEG,payload=26 ! "
            "rtpjpegdepay ! jpegdec ! videoconvert ! appsink"
        )
        
        try:
            self._capture = cv2.VideoCapture(gst_pipeline, cv2.CAP_GSTREAMER)
        except Exception:
            # Fallback para OpenCV padrão
            self._capture = cv2.VideoCapture(gige_url)
        
        if not self._capture.isOpened():
            logger.error("gige_open_failed", ip=self.ip, port=self.port)
            raise StreamSourceError(
                f"Não foi possível abrir câmera GigE: {self.ip}:{self.port}",
                {"ip": self.ip, "port": self.port}
            )
        
        self._is_open = True
        self._start_time = time.time()
        
        props = self.get_properties()
        logger.info(
            "gige_opened",
            ip=self.ip,
            port=self.port,
            width=props.get("width"),
            height=props.get("height"),
        )
        
        return True
    
    def read(self) -> Optional[FrameInfo]:
        """Lê um frame da câmera."""
        if not self._is_open or self._capture is None:
            return None
        
        ret, frame = self._capture.read()
        
        if not ret:
            logger.warning("gige_read_failed", ip=self.ip)
            return None
        
        return self._create_frame_info(frame)


class GenTLHarvesterAdapter(BaseSourceAdapter):
    """
    Adaptador para câmeras GenTL via Harvester (ex.: Omron Sentech GigE).
    
    Usa a biblioteca harvesters (GenICam/GenTL). Requer arquivo CTI do fabricante.
    Opcionalmente redimensiona frames (max_dimension no lado maior) e usa target_fps
    configuráveis para não travar a UI e a inferência.
    """

    def __init__(
        self,
        cti_path: str,
        device_index: int = 0,
        fetch_timeout_ms: int = 3000,
        max_dimension: int = 1920,
        target_fps: float = 15.0,
    ):
        super().__init__(SourceType.GENTL)
        self.cti_path = Path(cti_path).resolve() if cti_path else None
        self.device_index = device_index
        self.fetch_timeout_ms = fetch_timeout_ms
        self._max_dimension = max_dimension if max_dimension > 0 else 0
        self._fps = float(target_fps)
        self._harvester = None
        self._ia = None
        self._width = 0
        self._height = 0

    def open(self) -> bool:
        """Abre a câmera via Harvester (GenTL)."""
        self._stop_requested = False
        try:
            from harvesters.core import Harvester
        except ImportError as e:
            logger.error("harvesters_not_installed", error=str(e))
            raise StreamSourceError(
                "Biblioteca 'harvesters' não instalada. Instale com: pip install harvesters",
                {"error": str(e)},
            ) from e

        if not self.cti_path or not self.cti_path.exists():
            logger.error("gentl_cti_not_found", path=str(self.cti_path))
            raise StreamSourceError(
                f"Arquivo CTI GenTL não encontrado: {self.cti_path}",
                {"cti_path": str(self.cti_path)},
            )

        h = Harvester()
        h.add_file(str(self.cti_path))
        h.update()

        if not h.device_info_list:
            h.reset()
            logger.error("gentl_no_devices_found")
            raise StreamSourceError(
                "Nenhuma câmera GenTL encontrada. Verifique o CTI e a conexão.",
                {"cti_path": str(self.cti_path)},
            )

        if self.device_index >= len(h.device_info_list):
            h.reset()
            raise StreamSourceError(
                f"Índice de câmera inválido: {self.device_index} (encontradas: {len(h.device_info_list)})",
                {"device_index": self.device_index, "count": len(h.device_info_list)},
            )

        self._harvester = h
        try:
            self._ia = h.create(self.device_index)
            self._ia.start()
        except Exception as e:
            err = str(e)
            try:
                h.reset()
            except Exception:
                pass
            self._harvester = None
            self._ia = None
            err_lower = err.lower()
            if "opened by another client" in err_lower or "requested operation is not allowed" in err_lower:
                raise StreamSourceError(
                    "A camera GenTL selecionada ja esta em uso por outro aplicativo/cliente. "
                    "Feche o software que esta usando a camera (ou outra instancia deste app) e tente novamente.",
                    {
                        "device_index": self.device_index,
                        "cti_path": str(self.cti_path),
                        "raw_error": err,
                    },
                ) from e
            raise StreamSourceError(
                f"Falha ao abrir camera GenTL no indice {self.device_index}: {err}",
                {"device_index": self.device_index, "cti_path": str(self.cti_path), "raw_error": err},
            ) from e
        # Não fazemos fetch() aqui: obter um frame 20MP na thread principal trava a UI.
        # Dimensões são preenchidas no primeiro read() (na thread do worker).

        self._is_open = True
        self._start_time = time.time()
        self._first_frame_logged = False
        logger.info(
            "gentl_opened",
            cti_path=str(self.cti_path),
            device_index=self.device_index,
        )
        return True

    # Limite de segurança: mesmo com max_dimension=0, não enviar frames > 1920 no lado maior
    _SAFETY_MAX_DIMENSION = 1920

    def _resize_if_needed(self, image: np.ndarray) -> np.ndarray:
        """Redimensiona o frame se exceder max_dimension (0 = não redimensionar; há limite de segurança)."""
        h, w = image.shape[:2]
        effective_max = self._max_dimension if self._max_dimension > 0 else self._SAFETY_MAX_DIMENSION
        if w <= effective_max and h <= effective_max:
            return image
        scale = min(effective_max / w, effective_max / h, 1.0)
        new_w = int(round(w * scale))
        new_h = int(round(h * scale))
        out = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
        self._width = new_w
        self._height = new_h
        if self._max_dimension <= 0 and (w > self._SAFETY_MAX_DIMENSION or h > self._SAFETY_MAX_DIMENSION):
            logger.debug("gentl_safety_cap_applied", original=(w, h), resized=(new_w, new_h))
        return out

    def read(self) -> Optional[FrameInfo]:
        """Lê um frame da câmera GenTL (redimensionado se necessário). Tudo roda na thread do worker."""
        if self._stop_requested or not self._is_open or self._ia is None:
            return None
        try:
            with self._ia.fetch(timeout=self.fetch_timeout_ms) as buffer:
                component = buffer.payload.components[0]
                native_w, native_h = component.width, component.height
                if not self._first_frame_logged:
                    self._width = native_w
                    self._height = native_h
                image = component.data.reshape(native_h, native_w)
                if len(image.shape) == 2:
                    image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
                image = self._resize_if_needed(image)
                if not self._first_frame_logged:
                    logger.info(
                        "gentl_first_frame",
                        native=(native_w, native_h),
                        output=(self._width, self._height),
                    )
                    self._first_frame_logged = True
                return self._create_frame_info(image)
        except Exception as e:
            if self._stop_requested:
                return None
            logger.warning("gentl_read_failed", error=str(e))
            return None

    def get_properties(self) -> Dict[str, Any]:
        """Retorna propriedades da fonte (sem cv2.VideoCapture)."""
        if not self._is_open:
            return {}
        return {
            "width": self._width,
            "height": self._height,
            "fps": self._fps,
            "frame_count": 0,
            "fourcc": 0,
        }

    def get_gentl_node_map(self):
        """Retorna o node map GenICam da câmera (para ajustes de gain, exposure, etc.)."""
        if not self._is_open or self._ia is None:
            return None
        try:
            return self._ia.remote_device.node_map
        except Exception as e:
            logger.warning("gentl_node_map_error", error=str(e))
            return None

    def get_gentl_features(self) -> Dict[str, Any]:
        """
        Lê parâmetros GenICam comuns (Gain, Exposure, Auto) da câmera.
        Retorna um dicionário com chaves: Gain, ExposureTime, ExposureAuto, GainAuto
        (apenas as que existirem no device). Cada valor é um dict com keys:
        value, min, max, writable; para Auto, value é string (e.g. "Off", "Continuous").
        """
        nm = self.get_gentl_node_map()
        if nm is None:
            return {}
        out = {}
        # Nomes comuns GenICam (Omron Sentech / GigE Vision)
        for node_name in ("Gain", "ExposureTime", "ExposureTimeAbs"):
            try:
                node = getattr(nm, node_name, None)
                if node is None:
                    continue
                val = getattr(node, "value", None)
                if val is None:
                    continue
                min_val = getattr(node, "min", None)
                max_val = getattr(node, "max", None)
                out[node_name] = {
                    "value": float(val),
                    "min": float(min_val) if min_val is not None else 0,
                    "max": float(max_val) if max_val is not None else val * 2,
                    "writable": True,
                }
            except Exception:
                pass
        # Auto features (enumeração: Off, Once, Continuous)
        for node_name in ("ExposureAuto", "GainAuto"):
            try:
                node = getattr(nm, node_name, None)
                if node is None:
                    continue
                val = getattr(node, "value", None)
                if val is None:
                    continue
                out[node_name] = {
                    "value": str(val) if not isinstance(val, str) else val,
                    "symbolics": getattr(node, "symbolics", None) or [],
                    "writable": True,
                }
            except Exception:
                pass
        return out

    def set_gentl_feature(self, name: str, value: Any) -> bool:
        """
        Define um parâmetro GenICam por nome (ex.: Gain, ExposureTime, ExposureAuto).
        Retorna True se aplicado com sucesso.
        """
        nm = self.get_gentl_node_map()
        if nm is None:
            return False
        try:
            node = getattr(nm, name, None)
            if node is None:
                return False
            node.value = value
            return True
        except Exception as e:
            logger.warning("gentl_set_feature_failed", name=name, error=str(e))
            return False

    def close(self) -> None:
        """Fecha a câmera e libera Harvester (todas as chamadas GenTL na mesma thread de captura)."""
        self._stop_requested = True
        if self._ia is not None:
            try:
                self._ia.stop()
            except Exception as e:
                logger.warning("gentl_stop_error", error=str(e))
            try:
                self._ia.destroy()
            except Exception as e:
                logger.warning("gentl_destroy_error", error=str(e))
            self._ia = None
        if self._harvester is not None:
            try:
                self._harvester.reset()
            except Exception as e:
                logger.warning("gentl_reset_error", error=str(e))
            self._harvester = None
        self._is_open = False
        gc.collect()
        logger.info("source_closed", source_type=self.source_type.value)


def create_adapter(
    source_type: str,
    video_path: str = "",
    camera_index: int = 0,
    rtsp_url: str = "",
    gige_ip: str = "",
    gige_port: int = 3956,
    gentl_cti_path: str = "",
    gentl_device_index: int = 0,
    gentl_max_dimension: int = 1920,
    gentl_target_fps: float = 15.0,
    loop_video: bool = True,
    **kwargs
) -> BaseSourceAdapter:
    """
    Factory para criar adaptadores de fonte.
    
    Args:
        source_type: Tipo de fonte (video, usb, rtsp, gige, gentl)
        video_path: Caminho para arquivo de vídeo
        camera_index: Índice da câmera USB
        rtsp_url: URL do stream RTSP
        gige_ip: IP da câmera GigE
        gige_port: Porta da câmera GigE
        gentl_cti_path: Caminho do arquivo CTI GenTL (Harvester, ex. Omron Sentech)
        gentl_device_index: Índice da câmera na lista GenTL
        gentl_max_dimension: Dimensão máx. do lado maior (px); 0 = sem redimensionar
        gentl_target_fps: FPS alvo do stream GenTL
        loop_video: Se True, faz loop do vídeo
    
    Returns:
        Instância do adaptador apropriado
    """
    source = SourceType(source_type)
    
    if source == SourceType.VIDEO:
        return VideoFileAdapter(video_path, loop=loop_video)
    elif source == SourceType.USB:
        return USBCameraAdapter(camera_index)
    elif source == SourceType.RTSP:
        return RTSPAdapter(rtsp_url)
    elif source == SourceType.GIGE:
        return GigECameraAdapter(gige_ip, gige_port)
    elif source == SourceType.GENTL:
        return GenTLHarvesterAdapter(
            gentl_cti_path,
            device_index=gentl_device_index,
            max_dimension=gentl_max_dimension,
            target_fps=gentl_target_fps,
        )
    else:
        raise ValueError(f"Tipo de fonte não suportado: {source_type}")
