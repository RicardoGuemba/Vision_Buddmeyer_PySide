# -*- coding: utf-8 -*-
"""Dataclass DetectedPackage e cálculo do ponto de pega seguro."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np

from detection.events import Detection


@dataclass
class DetectedPackage:
    object_id: int
    class_id: int
    confidence: float
    mask: np.ndarray
    centroid_px: Tuple[int, int]
    pick_point_px: Tuple[int, int]
    area_px: int
    orientation_deg: float


def calculate_safe_pick_point(mask: np.ndarray) -> Optional[Tuple[int, int]]:
    """Ponto mais interno da máscara via distance transform."""
    if mask is None:
        return None
    binary = (mask > 0).astype(np.uint8)
    if binary.sum() == 0:
        return None
    try:
        import cv2
    except ImportError:
        ys, xs = np.where(binary > 0)
        return int(xs.mean()), int(ys.mean())

    distance_map = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
    _, max_distance, _, max_location = cv2.minMaxLoc(distance_map)
    if max_distance <= 0:
        return None
    return int(max_location[0]), int(max_location[1])


def detection_to_package(det: Detection, object_id: int = 0) -> Optional[DetectedPackage]:
    """Converte Detection do pipeline Mask2Former em DetectedPackage."""
    if det.mask is None:
        cx, cy = det.centroid
        pick = (int(cx), int(cy))
        area = int(det.effective_area_px or det.bbox.area)
        return DetectedPackage(
            object_id=object_id,
            class_id=int(det.class_id),
            confidence=float(det.confidence),
            mask=np.zeros((1, 1), dtype=np.uint8),
            centroid_px=(int(cx), int(cy)),
            pick_point_px=pick,
            area_px=area,
            orientation_deg=float(det.angle_deg or 0.0),
        )

    pick = calculate_safe_pick_point(det.mask)
    if pick is None:
        return None
    cx, cy = det.centroid
    area = int(det.area_px if det.area_px is not None else det.mask.sum())
    return DetectedPackage(
        object_id=object_id,
        class_id=int(det.class_id),
        confidence=float(det.confidence),
        mask=det.mask,
        centroid_px=(int(cx), int(cy)),
        pick_point_px=pick,
        area_px=area,
        orientation_deg=float(det.angle_deg or 0.0),
    )
