# -*- coding: utf-8
"""Testes do VisionSupervisor (seleção + payload CLP)."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _make_detection(confidence: float, area_px: float, centroid=(100.0, 175.0)):
    from detection.events import BoundingBox, Detection

    return Detection(
        bbox=BoundingBox(0, 0, 50, 50),
        confidence=confidence,
        class_id=0,
        class_name="Embalagem",
        mask=np.ones((50, 50), dtype=bool),
        centroid_override=centroid,
        angle_deg=15.0,
        area_px=area_px,
    )


@pytest.fixture
def app(qtbot):
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


class TestVisionSupervisor:
    def test_build_plc_payload_clamps_roi(self, qtbot, app):
        from detection.events import DetectionResult
        from control.supervisor import VisionSupervisor
        from communication.connection_state import ConnectionState, ConnectionStatus
        from config.settings import Settings, PreprocessSettings

        settings = Settings(preprocess=PreprocessSettings(roi_calibration_mm_per_px=10.0))
        cip = MagicMock()
        cip._state = ConnectionState(
            status=ConnectionStatus.CONNECTED,
            ip="192.168.1.10",
            port=44818,
        )
        supervisor = VisionSupervisor(cip, settings=settings)
        supervisor.set_roi_getter(lambda: (True, [100, 100, 200, 150]))

        det = _make_detection(confidence=0.9, area_px=2500.0, centroid=(30.0, 175.0))
        result = DetectionResult(detections=[det])
        payload = supervisor.build_plc_payload(result)

        mm_per_px = 10.0
        assert payload is not None
        assert payload["centroid_x"] == pytest.approx(100.0 * mm_per_px)
        assert payload["centroid_y"] == pytest.approx(175.0 * mm_per_px)
        assert payload["area"] == pytest.approx(2500.0 * mm_per_px ** 2)

    def test_send_pick_target_writes_cip(self, qtbot, app):
        import asyncio
        from detection.events import DetectionResult
        from control.supervisor import VisionSupervisor
        from communication.connection_state import ConnectionState, ConnectionStatus

        cip = MagicMock()
        cip._state = ConnectionState(
            status=ConnectionStatus.CONNECTED,
            ip="192.168.1.10",
            port=44818,
        )
        cip.read_tag = AsyncMock(return_value=True)
        cip.write_detection_result = AsyncMock()

        supervisor = VisionSupervisor(cip)
        supervisor.set_roi_getter(lambda: (False, None))

        closer = _make_detection(confidence=0.85, area_px=8000.0)
        farther = _make_detection(confidence=0.95, area_px=1000.0)
        result = DetectionResult(detections=[closer, farther])

        loop = asyncio.new_event_loop()
        try:
            ok = loop.run_until_complete(supervisor.send_pick_target(result))
        finally:
            loop.close()

        assert ok is True
        cip.write_detection_result.assert_awaited_once()
        kwargs = cip.write_detection_result.await_args.kwargs
        assert kwargs["detected"] is True
        assert kwargs["confidence"] == pytest.approx(0.85)
