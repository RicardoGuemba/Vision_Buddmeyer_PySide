# -*- coding: utf-8 -*-
"""Testes unitários do clamp de centroide ao ROI."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestClampCentroidToRoi:
    """Testes da função clamp_centroid_to_roi (projeção ortogonal ao ROI)."""

    def test_point_inside_roi_unchanged(self):
        """Ponto dentro do ROI permanece inalterado."""
        from preprocessing.roi_manager import clamp_centroid_to_roi, ROI

        roi = (100, 100, 200, 150)  # x, y, w, h
        cx, cy = 150.0, 175.0
        out_x, out_y = clamp_centroid_to_roi(cx, cy, roi)
        assert out_x == 150.0
        assert out_y == 175.0

    def test_point_outside_left_clamped(self):
        """Ponto à esquerda do ROI é projetado na borda esquerda."""
        from preprocessing.roi_manager import clamp_centroid_to_roi

        roi = (100, 100, 200, 150)
        cx, cy = 50.0, 175.0
        out_x, out_y = clamp_centroid_to_roi(cx, cy, roi)
        assert out_x == 100.0
        assert out_y == 175.0

    def test_point_outside_right_clamped(self):
        """Ponto à direita do ROI é projetado na borda direita."""
        from preprocessing.roi_manager import clamp_centroid_to_roi

        roi = (100, 100, 200, 150)
        cx, cy = 350.0, 175.0
        out_x, out_y = clamp_centroid_to_roi(cx, cy, roi)
        assert out_x == 300.0  # x + width
        assert out_y == 175.0

    def test_point_outside_top_clamped(self):
        """Ponto acima do ROI é projetado na borda superior."""
        from preprocessing.roi_manager import clamp_centroid_to_roi

        roi = (100, 100, 200, 150)
        cx, cy = 200.0, 50.0
        out_x, out_y = clamp_centroid_to_roi(cx, cy, roi)
        assert out_x == 200.0
        assert out_y == 100.0

    def test_point_outside_bottom_clamped(self):
        """Ponto abaixo do ROI é projetado na borda inferior."""
        from preprocessing.roi_manager import clamp_centroid_to_roi

        roi = (100, 100, 200, 150)
        cx, cy = 200.0, 300.0
        out_x, out_y = clamp_centroid_to_roi(cx, cy, roi)
        assert out_x == 200.0
        assert out_y == 250.0  # y + height

    def test_point_outside_corner_clamped(self):
        """Ponto em canto externo é projetado no canto mais próximo."""
        from preprocessing.roi_manager import clamp_centroid_to_roi

        roi = (100, 100, 200, 150)
        cx, cy = 50.0, 50.0
        out_x, out_y = clamp_centroid_to_roi(cx, cy, roi)
        assert out_x == 100.0
        assert out_y == 100.0

    def test_point_on_edge_unchanged(self):
        """Ponto exatamente na borda permanece inalterado."""
        from preprocessing.roi_manager import clamp_centroid_to_roi

        roi = (100, 100, 200, 150)
        out_x, out_y = clamp_centroid_to_roi(100.0, 100.0, roi)
        assert out_x == 100.0
        assert out_y == 100.0

        out_x, out_y = clamp_centroid_to_roi(300.0, 250.0, roi)
        assert out_x == 300.0
        assert out_y == 250.0

    def test_accepts_roi_instance(self):
        """Aceita instância de ROI além de tupla."""
        from preprocessing.roi_manager import clamp_centroid_to_roi, ROI

        r = ROI(x=50, y=50, width=100, height=80)
        cx, cy = 200.0, 200.0
        out_x, out_y = clamp_centroid_to_roi(cx, cy, r)
        assert out_x == 150.0  # 50 + 100
        assert out_y == 130.0  # 50 + 80
