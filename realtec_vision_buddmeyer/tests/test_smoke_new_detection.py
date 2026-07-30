# -*- coding: utf-8 -*-
"""Smoke: novo movimento da embalagem → motor 1× (~1 s)."""

from __future__ import annotations

from pathlib import Path
import sys
from unittest.mock import MagicMock

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import Mark2Settings, Mark2OperationSettings
from detection.events import BoundingBox, Detection, DetectionResult
from robot.mark2_controller import Mark2Controller
from robot.robot_state import RobotState
from robot.robot_worker import RobotTask


def _result(x: float = 30.0, y: float = 30.0, conf: float = 0.9) -> DetectionResult:
    det = Detection(
        bbox=BoundingBox(x - 20, y - 20, x + 20, y + 20),
        confidence=conf,
        class_id=0,
        class_name="Embalagem",
        mask=np.ones((40, 40), dtype=np.uint8),
        centroid_override=(x, y),
        area_px=1600.0,
        angle_deg=0.0,
    )
    return DetectionResult(detections=[det])


def _empty() -> DetectionResult:
    return DetectionResult(detections=[])


@pytest.fixture
def smoke_controller():
    mark2 = Mark2Settings(
        operation=Mark2OperationSettings(
            smoke_detection_trigger=True,
            smoke_cooldown_seconds=0.0,
            smoke_hold_seconds=1.0,
            smoke_movement_tolerance_px=18.0,
            enabled=True,
        )
    )
    worker = MagicMock()
    worker.isRunning.return_value = True
    worker.serial.angles = {"base": 90, "shoulder": 90, "elbow": 90, "gripper": 110}
    ctrl = Mark2Controller(mark2=mark2, worker=worker)
    ctrl._state = RobotState.IDLE
    return ctrl, worker


class TestSmokeMovementTrigger:
    def test_first_sighting_triggers(self, smoke_controller):
        ctrl, worker = smoke_controller
        ctrl.process_detection_result(_result(10, 10))
        assert worker.enqueue.called
        task = worker.enqueue.call_args[0][0]
        assert task.kind == "smoke"
        assert task.payload.get("hold_seconds") == 1.0

    def test_small_jitter_does_not_retrigger(self, smoke_controller):
        ctrl, worker = smoke_controller
        ctrl.process_detection_result(_result(100, 100))
        worker.enqueue.reset_mock()
        ctrl._state = RobotState.IDLE
        # movimento < 18 px
        ctrl.process_detection_result(_result(105, 100))
        assert worker.enqueue.call_count == 0

    def test_significant_move_triggers_once(self, smoke_controller):
        ctrl, worker = smoke_controller
        ctrl.process_detection_result(_result(100, 100))
        worker.enqueue.reset_mock()
        ctrl._state = RobotState.IDLE
        ctrl.process_detection_result(_result(130, 100))  # 30 px
        assert worker.enqueue.call_count == 1
        assert worker.enqueue.call_args[0][0].kind == "smoke"

    def test_leave_fov_clears_and_reappear_triggers(self, smoke_controller):
        ctrl, worker = smoke_controller
        ctrl.process_detection_result(_result(50, 50))
        worker.enqueue.reset_mock()
        ctrl._state = RobotState.IDLE
        ctrl.process_detection_result(_empty())
        assert ctrl._smoke_last_trigger_point is None
        ctrl.process_detection_result(_result(50, 50))
        assert worker.enqueue.call_count == 1
