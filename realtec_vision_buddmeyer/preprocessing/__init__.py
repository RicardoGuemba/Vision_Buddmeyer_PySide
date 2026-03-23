# -*- coding: utf-8 -*-
"""
Módulo de pré-processamento do sistema Buddmeyer Vision v2.0
"""

from .roi_manager import ROIManager, ROI, clamp_centroid_to_roi

__all__ = [
    "ROIManager",
    "ROI",
    "clamp_centroid_to_roi",
]
