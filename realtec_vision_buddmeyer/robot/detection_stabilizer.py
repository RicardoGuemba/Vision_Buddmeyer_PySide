# -*- coding: utf-8 -*-
"""Estabilização de detecções em múltiplos frames antes de mover o robô."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional, Tuple

from .detected_package import DetectedPackage


@dataclass
class StabilizerConfig:
    minimum_confidence: float = 0.85
    stable_frames: int = 5
    point_tolerance_px: float = 4.0
    maximum_area_variation: float = 0.10


class DetectionStabilizer:
    """Exige N frames consistentes do mesmo alvo antes de validar."""

    def __init__(self, config: Optional[StabilizerConfig] = None) -> None:
        self.config = config or StabilizerConfig()
        self._history: Deque[DetectedPackage] = deque(maxlen=self.config.stable_frames)
        self._locked: Optional[DetectedPackage] = None

    def reset(self) -> None:
        self._history.clear()
        self._locked = None

    @property
    def locked_package(self) -> Optional[DetectedPackage]:
        return self._locked

    def update(self, package: Optional[DetectedPackage], robot_idle: bool) -> Optional[DetectedPackage]:
        """
        Alimenta um frame. Retorna DetectedPackage estável ou None.
        Só estabiliza se robot_idle=True.
        """
        if not robot_idle:
            return None
        if package is None or package.confidence < self.config.minimum_confidence:
            self._history.clear()
            return None

        if self._history:
            ref = self._history[-1]
            if not self._same_target(ref, package):
                self._history.clear()

        self._history.append(package)
        if len(self._history) < self.config.stable_frames:
            return None

        if not self._is_stable():
            return None

        confs = [p.confidence for p in self._history]
        if sum(confs) / len(confs) < self.config.minimum_confidence:
            return None

        # média do ponto de pega
        xs = [p.pick_point_px[0] for p in self._history]
        ys = [p.pick_point_px[1] for p in self._history]
        areas = [p.area_px for p in self._history]
        avg = DetectedPackage(
            object_id=package.object_id,
            class_id=package.class_id,
            confidence=sum(confs) / len(confs),
            mask=package.mask,
            centroid_px=(
                int(sum(p.centroid_px[0] for p in self._history) / len(self._history)),
                int(sum(p.centroid_px[1] for p in self._history) / len(self._history)),
            ),
            pick_point_px=(int(sum(xs) / len(xs)), int(sum(ys) / len(ys))),
            area_px=int(sum(areas) / len(areas)),
            orientation_deg=package.orientation_deg,
        )
        self._locked = avg
        self._history.clear()
        return avg

    def _same_target(self, a: DetectedPackage, b: DetectedPackage) -> bool:
        dx = a.pick_point_px[0] - b.pick_point_px[0]
        dy = a.pick_point_px[1] - b.pick_point_px[1]
        dist = (dx * dx + dy * dy) ** 0.5
        if dist > self.config.point_tolerance_px * 3:
            return False
        if a.area_px <= 0 or b.area_px <= 0:
            return True
        ratio = abs(a.area_px - b.area_px) / max(a.area_px, b.area_px)
        return ratio <= self.config.maximum_area_variation * 3

    def _is_stable(self) -> bool:
        pts = [p.pick_point_px for p in self._history]
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        for x, y in pts:
            if ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 > self.config.point_tolerance_px:
                return False
        areas = [p.area_px for p in self._history]
        mean_a = sum(areas) / len(areas)
        if mean_a <= 0:
            return False
        for a in areas:
            if abs(a - mean_a) / mean_a > self.config.maximum_area_variation:
                return False
        return True
