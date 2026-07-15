# -*- coding: utf-8 -*-
"""Testes unitários do overlay ROI (linhas verdes, sem crop)."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def app(qtbot):
    """Garante QApplication existente para widgets Qt."""
    return QApplication.instance() or QApplication([])


class TestRoiOverlay:
    """Testes do overlay ROI (apenas marcação verde, sem crop)."""

    def test_roi_overlay_preserves_frame_size(self, qtbot, app):
        """ROI overlay mantém dimensões do frame (não corta)."""
        from ui.pages.operation_page import OperationPage

        page = OperationPage()
        qtbot.addWidget(page)

        page._status_panel.get_roi = MagicMock(return_value=(True, [50, 50, 100, 100]))

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = page._draw_roi_overlay_if_enabled(frame)

        assert result.shape == frame.shape
        assert result is not frame

    def test_roi_overlay_disabled_returns_original(self, qtbot, app):
        """Com ROI desativado, retorna frame original."""
        from ui.pages.operation_page import OperationPage

        page = OperationPage()
        qtbot.addWidget(page)
        page._status_panel.get_roi = MagicMock(return_value=(False, None))

        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        result = page._draw_roi_overlay_if_enabled(frame)

        assert result.shape == frame.shape
        np.testing.assert_array_equal(result, frame)

    def test_roi_overlay_empty_coords_returns_original(self, qtbot, app):
        """Com coords vazias, retorna frame original."""
        from ui.pages.operation_page import OperationPage

        page = OperationPage()
        qtbot.addWidget(page)
        page._status_panel.get_roi = MagicMock(return_value=(True, []))

        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        result = page._draw_roi_overlay_if_enabled(frame)

        assert result.shape == frame.shape


class TestRoiClampCentroidCommunication:
    """Clamp de centroide no payload CLP via VisionSupervisor."""

    def test_centroid_clamped_when_roi_enabled(self, qtbot, app):
        from detection.events import Detection, DetectionResult, BoundingBox
        from config.settings import Settings, PreprocessSettings
        from control.supervisor import VisionSupervisor

        settings = Settings(preprocess=PreprocessSettings(roi_calibration_mm_per_px=10.0))
        supervisor = VisionSupervisor(MagicMock(), settings=settings)
        supervisor.set_roi_getter(lambda: (True, [100, 100, 200, 150]))

        det = Detection(
            bbox=BoundingBox(0, 0, 50, 50),
            confidence=0.9,
            class_id=0,
            class_name="Embalagem",
            mask=np.ones((50, 50), dtype=bool),
            centroid_override=(30.0, 175.0),
            area_px=1000.0,
        )
        result = DetectionResult(detections=[det])
        payload = supervisor.build_plc_payload(result)

        assert payload is not None
        assert payload["centroid_x"] == pytest.approx(100.0 * 10.0)
        assert payload["centroid_y"] == pytest.approx(175.0 * 10.0)

    def test_centroid_not_clamped_when_roi_disabled(self, qtbot, app):
        from detection.events import Detection, DetectionResult, BoundingBox
        from config.settings import Settings, PreprocessSettings
        from control.supervisor import VisionSupervisor

        settings = Settings(preprocess=PreprocessSettings(roi_calibration_mm_per_px=10.0))
        supervisor = VisionSupervisor(MagicMock(), settings=settings)
        supervisor.set_roi_getter(lambda: (False, None))

        det = Detection(
            bbox=BoundingBox(0, 0, 50, 50),
            confidence=0.9,
            class_id=0,
            class_name="Embalagem",
            mask=np.ones((50, 50), dtype=bool),
            centroid_override=(30.0, 175.0),
            area_px=1000.0,
        )
        result = DetectionResult(detections=[det])
        payload = supervisor.build_plc_payload(result)

        assert payload is not None
        assert payload["centroid_x"] == pytest.approx(30.0 * 10.0)
        assert payload["centroid_y"] == pytest.approx(175.0 * 10.0)
