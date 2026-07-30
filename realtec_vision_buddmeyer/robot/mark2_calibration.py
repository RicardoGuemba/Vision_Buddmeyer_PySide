# -*- coding: utf-8 -*-
"""Calibração pixel ↔ mundo ↔ referencial Mark2."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Sequence, Tuple

import numpy as np

from config.settings import Mark2CalibrationSettings, Mark2ReferenceSettings, Mark2WorkspaceSettings


@dataclass
class CoordinateTriple:
    pixel: Tuple[float, float]
    world_mm: Optional[Tuple[float, float]]
    robot_mm: Optional[Tuple[float, float]]
    reachable: bool
    message: str = ""


class Mark2Calibration:
    """Homografia + transformação rígida para o Mark2."""

    def __init__(
        self,
        calibration: Optional[Mark2CalibrationSettings] = None,
        reference: Optional[Mark2ReferenceSettings] = None,
        workspace: Optional[Mark2WorkspaceSettings] = None,
    ) -> None:
        self.calibration = calibration or Mark2CalibrationSettings()
        self.reference = reference or Mark2ReferenceSettings()
        self.workspace = workspace or Mark2WorkspaceSettings()
        self._H: Optional[np.ndarray] = None
        if self.calibration.homography:
            self._H = np.array(self.calibration.homography, dtype=np.float64)

    @property
    def is_calibrated(self) -> bool:
        if self._H is None:
            return False
        rmse = self.calibration.validation_rmse_mm
        if rmse is None:
            return True
        return rmse <= self.calibration.max_rmse_mm

    def set_reference(self, origin_x: float, origin_y: float, rotation_deg: float) -> None:
        self.reference.origin_x_mm = float(origin_x)
        self.reference.origin_y_mm = float(origin_y)
        self.reference.rotation_deg = float(rotation_deg)

    def compute_homography(
        self,
        image_points: Sequence[Sequence[float]],
        world_points_mm: Sequence[Sequence[float]],
    ) -> np.ndarray:
        if len(image_points) < self.calibration.min_homography_points:
            raise ValueError(
                f"Necessário ≥{self.calibration.min_homography_points} pontos"
            )
        if len(image_points) != len(world_points_mm):
            raise ValueError("image_points e world_points_mm devem ter o mesmo comprimento")

        src = np.array(image_points, dtype=np.float32)
        dst = np.array(world_points_mm, dtype=np.float32)
        try:
            import cv2
            H, mask = cv2.findHomography(src, dst, method=0)
        except Exception:
            H = self._homography_dlts(src, dst)
            mask = None
        if H is None:
            raise ValueError("Homografia degenerada / falhou")
        self._H = np.array(H, dtype=np.float64)
        self.calibration.homography = self._H.tolist()
        self.calibration.image_points = [list(map(float, p)) for p in image_points]
        self.calibration.world_points_mm = [list(map(float, p)) for p in world_points_mm]
        return self._H

    @staticmethod
    def _homography_dlts(src: np.ndarray, dst: np.ndarray) -> Optional[np.ndarray]:
        """DLT simples quando OpenCV não está disponível."""
        n = src.shape[0]
        A = []
        for i in range(n):
            x, y = src[i]
            u, v = dst[i]
            A.append([-x, -y, -1, 0, 0, 0, x * u, y * u, u])
            A.append([0, 0, 0, -x, -y, -1, x * v, y * v, v])
        A = np.asarray(A, dtype=np.float64)
        _, _, Vt = np.linalg.svd(A)
        H = Vt[-1].reshape(3, 3)
        if abs(H[2, 2]) < 1e-12:
            return None
        H = H / H[2, 2]
        return H

    def pixel_to_world(self, u: float, v: float) -> Tuple[float, float]:
        if self._H is None:
            raise RuntimeError("Homografia não definida")
        try:
            import cv2
            point = np.array([[[u, v]]], dtype=np.float32)
            transformed = cv2.perspectiveTransform(point, self._H.astype(np.float32))
            x_mm, y_mm = transformed[0, 0]
            return float(x_mm), float(y_mm)
        except Exception:
            vec = self._H @ np.array([u, v, 1.0], dtype=np.float64)
            if abs(vec[2]) < 1e-12:
                raise RuntimeError("Transformação degenerada")
            return float(vec[0] / vec[2]), float(vec[1] / vec[2])

    def world_to_robot(self, x_world: float, y_world: float) -> Tuple[float, float]:
        dx = x_world - self.reference.origin_x_mm
        dy = y_world - self.reference.origin_y_mm
        theta = math.radians(self.reference.rotation_deg)
        rotation = np.array(
            [
                [math.cos(theta), math.sin(theta)],
                [-math.sin(theta), math.cos(theta)],
            ],
            dtype=np.float64,
        )
        x_robot, y_robot = rotation @ np.array([dx, dy], dtype=np.float64)
        return float(x_robot), float(y_robot)

    def pixel_to_robot(self, u: float, v: float) -> Tuple[float, float]:
        xw, yw = self.pixel_to_world(u, v)
        return self.world_to_robot(xw, yw)

    def is_reachable(self, x_robot: float, y_robot: float, z_mm: float = 0.0) -> bool:
        r = math.hypot(x_robot, y_robot)
        if r < self.workspace.min_radius_mm or r > self.workspace.max_radius_mm:
            return False
        if z_mm < self.workspace.min_z_mm or z_mm > self.workspace.max_z_mm:
            return False
        return True

    def project(self, u: float, v: float, z_mm: float = 0.0) -> CoordinateTriple:
        if self._H is None:
            return CoordinateTriple(
                pixel=(u, v),
                world_mm=None,
                robot_mm=None,
                reachable=False,
                message="Sem homografia",
            )
        try:
            world = self.pixel_to_world(u, v)
            robot = self.world_to_robot(*world)
            ok = self.is_reachable(robot[0], robot[1], z_mm)
            return CoordinateTriple(
                pixel=(u, v),
                world_mm=world,
                robot_mm=robot,
                reachable=ok,
                message="" if ok else "Fora do workspace",
            )
        except Exception as exc:
            return CoordinateTriple(
                pixel=(u, v),
                world_mm=None,
                robot_mm=None,
                reachable=False,
                message=str(exc),
            )

    def validate_points(
        self,
        image_points: Sequence[Sequence[float]],
        world_points_mm: Sequence[Sequence[float]],
    ) -> float:
        """Calcula RMSE em mm e actualiza calibration.validation_rmse_mm."""
        if len(image_points) < 1:
            raise ValueError("Pontos de validação vazios")
        errors = []
        for (u, v), (xw, yw) in zip(image_points, world_points_mm):
            px, py = self.pixel_to_world(float(u), float(v))
            errors.append((px - float(xw)) ** 2 + (py - float(yw)) ** 2)
        rmse = float(math.sqrt(sum(errors) / len(errors)))
        self.calibration.validation_rmse_mm = rmse
        self.calibration.calibrated_at = datetime.now(timezone.utc).isoformat()
        return rmse

    def to_settings(self) -> Mark2CalibrationSettings:
        return self.calibration
