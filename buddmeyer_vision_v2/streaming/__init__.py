# -*- coding: utf-8 -*-
"""
Módulo de streaming de vídeo do sistema Buddmeyer Vision v2.0
"""

from .stream_manager import StreamManager
from .source_adapters import (
    SourceType,
    BaseSourceAdapter,
    VideoFileAdapter,
    USBCameraAdapter,
    RTSPAdapter,
    GigECameraAdapter,
)
from .frame_buffer import FrameBuffer, FrameInfo
from .rtsp_server import (
    RTSPStreamServer,
    MockRTSPServer,
    create_rtsp_server,
)

__all__ = [
    "StreamManager",
    "SourceType",
    "BaseSourceAdapter",
    "VideoFileAdapter",
    "USBCameraAdapter",
    "RTSPAdapter",
    "GigECameraAdapter",
    "FrameBuffer",
    "FrameInfo",
    "RTSPStreamServer",
    "MockRTSPServer",
    "create_rtsp_server",
]
