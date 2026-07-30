# -*- coding: utf-8 -*-
"""Cinemática inversa 2-link do Mark2."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple

from config.settings import Mark2GeometrySettings, Mark2ServosSettings


@dataclass
class JointAngles:
    base: int
    shoulder: int
    elbow: int


class Mark2KinematicsError(Exception):
    pass


class Mark2Kinematics:
    """
    IK plana: base no plano XY; ombro/cotovelo no plano radial-Z.

    L1 = ombro→cotovelo, L2 = cotovelo→garra, H0 = altura do ombro.
    """

    def __init__(
        self,
        geometry: Optional[Mark2GeometrySettings] = None,
        servos: Optional[Mark2ServosSettings] = None,
    ) -> None:
        self.geometry = geometry or Mark2GeometrySettings()
        self.servos = servos or Mark2ServosSettings()

    def inverse(self, x_mm: float, y_mm: float, z_mm: float) -> JointAngles:
        l1 = float(self.geometry.link_1_mm)
        l2 = float(self.geometry.link_2_mm)
        h0 = float(self.geometry.shoulder_height_mm)

        if l1 <= 0 or l2 <= 0:
            raise Mark2KinematicsError(
                "geometry.link_1_mm e link_2_mm devem ser medidos (>0)"
            )

        r = math.hypot(x_mm, y_mm)
        base_rad = math.atan2(y_mm, x_mm)
        # altura relativa ao eixo do ombro
        z_rel = z_mm - h0

        dist = math.hypot(r, z_rel)
        max_reach = l1 + l2
        min_reach = abs(l1 - l2)
        if dist > max_reach + 1e-6 or dist < min_reach - 1e-6:
            raise Mark2KinematicsError(f"Alvo fora do alcance: dist={dist:.1f} mm")

        # lei dos cossenos
        cos_elbow = (l1 * l1 + l2 * l2 - dist * dist) / (2 * l1 * l2)
        cos_elbow = max(-1.0, min(1.0, cos_elbow))
        # ângulo de flexão do cotovelo (0 = estendido)
        elbow_rad = math.acos(cos_elbow)

        cos_shoulder = (l1 * l1 + dist * dist - l2 * l2) / (2 * l1 * dist)
        cos_shoulder = max(-1.0, min(1.0, cos_shoulder))
        alpha = math.acos(cos_shoulder)
        gamma = math.atan2(z_rel, r)
        shoulder_rad = gamma + alpha

        base_deg = math.degrees(base_rad)
        shoulder_deg = math.degrees(shoulder_rad)
        elbow_deg = math.degrees(elbow_rad)

        return JointAngles(
            base=self._to_servo("base", base_deg),
            shoulder=self._to_servo("shoulder", shoulder_deg),
            elbow=self._to_servo("elbow", elbow_deg),
        )

    def _to_servo(self, joint: str, kinematic_deg: float) -> int:
        cfg = getattr(self.servos, joint)
        raw = cfg.zero + cfg.direction * kinematic_deg
        angle = int(round(raw))
        if angle < cfg.minimum or angle > cfg.maximum:
            raise Mark2KinematicsError(
                f"{joint} fora dos limites: {angle} not in [{cfg.minimum},{cfg.maximum}]"
            )
        return angle

    def reachable_xy(self, x_mm: float, y_mm: float, z_mm: float) -> bool:
        try:
            self.inverse(x_mm, y_mm, z_mm)
            return True
        except Mark2KinematicsError:
            return False
