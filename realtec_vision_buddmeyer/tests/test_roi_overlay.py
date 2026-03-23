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

        # Simula ROI ativo com coordenadas
        page._status_panel.get_roi = MagicMock(return_value=(True, [50, 50, 100, 100]))

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = page._draw_roi_overlay_if_enabled(frame)

        assert result.shape == frame.shape
        assert result is not frame  # cópia com overlay

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
    """Testes funcionais do clamp de centroide ao enviar ao CLP."""

    def test_centroid_clamped_when_roi_enabled(self, qtbot, app):
        """Quando ROI está ativo, centroide fora do ROI é limitado ao ROI."""
        from unittest.mock import MagicMock, AsyncMock, patch
        from detection.events import DetectionEvent

        from ui.pages.operation_page import OperationPage

        page = OperationPage()
        qtbot.addWidget(page)

        # ROI: x=100, y=100, w=200, h=150
        page._status_panel.get_roi = MagicMock(return_value=(True, [100, 100, 200, 150]))
        # Detecção com centroide fora do ROI (à esquerda): centro (30, 175)
        from detection.events import DetectionEvent
        det = DetectionEvent(
            detected=True,
            centroid=(30.0, 175.0),
            confidence=0.9,
            detection_count=1,
            inference_time_ms=10.0,
        )
        page._last_best_detection = det
        page._frame_count = 100
        from communication.connection_state import ConnectionState, ConnectionStatus
        page._cip_client._state = ConnectionState(
            status=ConnectionStatus.CONNECTED,
            ip="192.168.1.10",
            port=44818,
        )

        sent_centroid = []

        async def capture_send(centroid_x, centroid_y, **kwargs):
            sent_centroid.append((centroid_x, centroid_y))

        def run_task(coro):
            import asyncio
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            loop.run_until_complete(coro)

        with patch.object(page, "_send_detection_to_plc", new=AsyncMock(side_effect=capture_send)):
            with patch("asyncio.create_task", side_effect=run_task):
                page._communicate_centroid_to_plc()

        assert len(sent_centroid) == 1
        cx_mm, cy_mm = sent_centroid[0]
        mm_per_px = getattr(page._settings.preprocess, "roi_calibration_mm_per_px", 1.0) or 1.0
        # Centroide (30, 175) seria projetado em (100, 175) dentro do ROI
        expected_x_mm = 100.0 * mm_per_px
        expected_y_mm = 175.0 * mm_per_px
        assert abs(cx_mm - expected_x_mm) < 1e-6
        assert abs(cy_mm - expected_y_mm) < 1e-6

    def test_centroid_not_clamped_when_roi_disabled(self, qtbot, app):
        """Quando ROI está desativado, centroide é enviado sem alteração."""
        from unittest.mock import MagicMock, AsyncMock, patch
        from detection.events import DetectionEvent

        from ui.pages.operation_page import OperationPage

        page = OperationPage()
        qtbot.addWidget(page)

        page._status_panel.get_roi = MagicMock(return_value=(False, [0, 0, 640, 480]))
        from detection.events import DetectionEvent
        det = DetectionEvent(
            detected=True,
            centroid=(30.0, 175.0),
            confidence=0.9,
            detection_count=1,
            inference_time_ms=10.0,
        )
        page._last_best_detection = det
        page._frame_count = 100
        from communication.connection_state import ConnectionState, ConnectionStatus
        page._cip_client._state = ConnectionState(
            status=ConnectionStatus.CONNECTED,
            ip="192.168.1.10",
            port=44818,
        )

        sent_centroid = []

        async def capture_send(centroid_x, centroid_y, **kwargs):
            sent_centroid.append((centroid_x, centroid_y))

        def run_task(coro):
            import asyncio
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            loop.run_until_complete(coro)

        with patch.object(page, "_send_detection_to_plc", new=AsyncMock(side_effect=capture_send)):
            with patch("asyncio.create_task", side_effect=run_task):
                page._communicate_centroid_to_plc()

        assert len(sent_centroid) == 1
        cx_mm, cy_mm = sent_centroid[0]
        mm_per_px = getattr(page._settings.preprocess, "roi_calibration_mm_per_px", 1.0) or 1.0
        # Sem clamp: centro (30, 175) -> mm
        expected_x_mm = 30.0 * mm_per_px
        expected_y_mm = 175.0 * mm_per_px
        assert abs(cx_mm - expected_x_mm) < 1e-6
        assert abs(cy_mm - expected_y_mm) < 1e-6
