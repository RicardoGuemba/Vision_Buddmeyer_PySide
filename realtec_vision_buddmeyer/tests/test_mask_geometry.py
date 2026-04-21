# -*- coding: utf-8 -*-
"""
Testes unitários de detection.mask_geometry.

Valida centróide, área e ângulo do eixo maior para máscaras sintéticas
com propriedades conhecidas (retângulo axis-aligned, retângulo rotacionado,
disco, quadrado com buraco).
"""

import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _axis_aligned_rect_mask(h: int, w: int, x: int, y: int, rw: int, rh: int) -> np.ndarray:
    mask = np.zeros((h, w), dtype=np.uint8)
    mask[y : y + rh, x : x + rw] = 1
    return mask


def _rotated_rect_mask(h: int, w: int, cx: float, cy: float, rw: float, rh: float, angle_deg: float) -> np.ndarray:
    """Rasteriza um retângulo de tamanho rw x rh centrado em (cx, cy), rotacionado."""
    yy, xx = np.mgrid[0:h, 0:w]
    dx = xx - cx
    dy = yy - cy
    theta = math.radians(-angle_deg)
    x_local = dx * math.cos(theta) - dy * math.sin(theta)
    y_local = dx * math.sin(theta) + dy * math.cos(theta)
    mask = ((np.abs(x_local) <= rw / 2) & (np.abs(y_local) <= rh / 2)).astype(np.uint8)
    return mask


class TestComputeMaskGeometry:
    def test_returns_none_for_empty_mask(self):
        from detection.mask_geometry import compute_mask_geometry

        mask = np.zeros((50, 50), dtype=np.uint8)
        assert compute_mask_geometry(mask, min_pixels=10) is None

    def test_returns_none_for_small_mask(self):
        from detection.mask_geometry import compute_mask_geometry

        mask = np.zeros((50, 50), dtype=np.uint8)
        mask[0, 0] = 1
        mask[0, 1] = 1
        assert compute_mask_geometry(mask, min_pixels=10) is None

    def test_centroid_and_area_axis_aligned_rect(self):
        from detection.mask_geometry import compute_mask_geometry

        mask = _axis_aligned_rect_mask(100, 100, x=20, y=30, rw=40, rh=20)
        geom = compute_mask_geometry(mask, min_pixels=10)
        assert geom is not None
        assert geom.area_px == 40 * 20
        assert geom.centroid_x == pytest.approx(20 + (40 - 1) / 2, abs=0.5)
        assert geom.centroid_y == pytest.approx(30 + (20 - 1) / 2, abs=0.5)

    def test_angle_zero_for_horizontal_rect(self):
        """Retângulo com lado maior horizontal -> ângulo próximo de 0 (ou 180)."""
        from detection.mask_geometry import compute_mask_geometry

        mask = _axis_aligned_rect_mask(100, 200, x=10, y=45, rw=180, rh=10)
        geom = compute_mask_geometry(mask, min_pixels=10)
        assert geom is not None
        angle = geom.angle_deg
        assert min(angle, 180.0 - angle) < 2.0

    def test_angle_90_for_vertical_rect(self):
        """Retângulo com lado maior vertical -> ângulo próximo de 90."""
        from detection.mask_geometry import compute_mask_geometry

        mask = _axis_aligned_rect_mask(200, 100, x=45, y=10, rw=10, rh=180)
        geom = compute_mask_geometry(mask, min_pixels=10)
        assert geom is not None
        assert abs(geom.angle_deg - 90.0) < 2.0

    @pytest.mark.parametrize("angle", [0, 15, 30, 45, 60, 75, 120, 150])
    def test_angle_matches_rotated_rect(self, angle):
        """Para cada ângulo, mask do retângulo rotacionado deve produzir esse ângulo."""
        from detection.mask_geometry import compute_mask_geometry

        mask = _rotated_rect_mask(300, 300, cx=150, cy=150, rw=120, rh=25, angle_deg=angle)
        geom = compute_mask_geometry(mask, min_pixels=200)
        assert geom is not None
        expected = angle % 180.0
        got = geom.angle_deg
        circular_diff = min(abs(got - expected), 180.0 - abs(got - expected))
        assert circular_diff < 5.0, f"esperado ~{expected}, obtido {got}"

    def test_elongation_greater_than_one_for_long_rect(self):
        from detection.mask_geometry import compute_mask_geometry

        mask = _axis_aligned_rect_mask(300, 300, x=50, y=140, rw=200, rh=20)
        geom = compute_mask_geometry(mask, min_pixels=100)
        assert geom is not None
        assert geom.elongation > 3.0

    def test_centroid_of_disc_is_center(self):
        """Disco: centróide no centro, ângulo indefinido mas determinístico."""
        from detection.mask_geometry import compute_mask_geometry

        yy, xx = np.mgrid[0:200, 0:200]
        mask = ((xx - 100) ** 2 + (yy - 100) ** 2 <= 50 ** 2).astype(np.uint8)
        geom = compute_mask_geometry(mask, min_pixels=100)
        assert geom is not None
        assert geom.centroid_x == pytest.approx(100.0, abs=1.0)
        assert geom.centroid_y == pytest.approx(100.0, abs=1.0)
        assert geom.elongation == pytest.approx(1.0, abs=0.1)


class TestMajorAxisEndpoints:
    def test_endpoints_pass_through_centroid(self):
        from detection.mask_geometry import compute_mask_geometry, major_axis_endpoints

        mask = _axis_aligned_rect_mask(200, 200, x=20, y=80, rw=160, rh=30)
        geom = compute_mask_geometry(mask, min_pixels=100)
        assert geom is not None
        (x0, y0), (x1, y1) = major_axis_endpoints(geom, length_scale=1.0)
        mid_x = (x0 + x1) / 2
        mid_y = (y0 + y1) / 2
        assert mid_x == pytest.approx(geom.centroid_x, abs=1e-6)
        assert mid_y == pytest.approx(geom.centroid_y, abs=1e-6)
