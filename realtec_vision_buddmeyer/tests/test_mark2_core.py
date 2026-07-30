# -*- coding: utf-8 -*-
"""Testes Mark2: serial, calibração, pick point, stabilizer, kinematics."""

from __future__ import annotations

import math
from unittest.mock import MagicMock

import numpy as np
import pytest

from config.settings import (
    Mark2GeometrySettings,
    Mark2ServosSettings,
    Mark2WorkspaceSettings,
    Mark2ReferenceSettings,
    Mark2CalibrationSettings,
)
from robot.detected_package import calculate_safe_pick_point, DetectedPackage
from robot.detection_stabilizer import DetectionStabilizer, StabilizerConfig
from robot.mark2_calibration import Mark2Calibration
from robot.mark2_kinematics import Mark2Kinematics, Mark2KinematicsError
from robot.mark2_serial import Mark2Serial, Mark2SerialError
from robot.robot_state import RobotState, VALID_TRANSITIONS


class FakeSerial:
    def __init__(self, *args, **kwargs):
        self.is_open = True
        self._lines = [b"READY\n"]
        self.written = []

    def write(self, data: bytes) -> int:
        self.written.append(data)
        cmd = data.decode().strip()
        if cmd.startswith("MOVE") or cmd == "HOME":
            self._lines.append(b"OK\n")
        elif cmd == "STOP":
            self._lines.append(b"STOPPED\n")
        return len(data)

    def readline(self) -> bytes:
        if self._lines:
            return self._lines.pop(0)
        return b""

    def close(self) -> None:
        self.is_open = False


class TestMark2Serial:
    def test_connect_ready_and_move(self):
        ser = Mark2Serial(serial_factory=lambda *a, **k: FakeSerial())
        assert ser.connect() == "READY"
        assert ser.move(90, 90, 90, 110, 15) == "OK"
        assert ser.home() == "OK"
        assert ser.stop() == "STOPPED"
        ser.disconnect()
        assert not ser.is_connected

    def test_error_when_disconnected(self):
        ser = Mark2Serial(serial_factory=lambda *a, **k: FakeSerial())
        with pytest.raises(Mark2SerialError):
            ser.move(90, 90, 90, 110, 15)


class TestPickPoint:
    def test_distance_transform_center(self):
        mask = np.zeros((50, 50), dtype=np.uint8)
        mask[10:40, 10:40] = 1
        pt = calculate_safe_pick_point(mask)
        assert pt is not None
        assert 20 <= pt[0] <= 30
        assert 20 <= pt[1] <= 30

    def test_empty_mask(self):
        assert calculate_safe_pick_point(np.zeros((10, 10), dtype=np.uint8)) is None


class TestStabilizer:
    def _pkg(self, x, y, conf=0.9, area=100):
        return DetectedPackage(
            object_id=0,
            class_id=0,
            confidence=conf,
            mask=np.ones((5, 5), dtype=np.uint8),
            centroid_px=(x, y),
            pick_point_px=(x, y),
            area_px=area,
            orientation_deg=0.0,
        )

    def test_requires_n_frames(self):
        stab = DetectionStabilizer(StabilizerConfig(stable_frames=3, point_tolerance_px=5))
        assert stab.update(self._pkg(10, 10), True) is None
        assert stab.update(self._pkg(11, 10), True) is None
        locked = stab.update(self._pkg(10, 11), True)
        assert locked is not None

    def test_ignores_when_busy(self):
        stab = DetectionStabilizer(StabilizerConfig(stable_frames=1))
        assert stab.update(self._pkg(10, 10), robot_idle=False) is None


class TestCalibration:
    def test_homography_and_roundtrip(self):
        cal = Mark2Calibration(
            Mark2CalibrationSettings(),
            Mark2ReferenceSettings(origin_x_mm=0, origin_y_mm=0, rotation_deg=0),
            Mark2WorkspaceSettings(min_radius_mm=0, max_radius_mm=500, min_z_mm=-10, max_z_mm=200),
        )
        img = [[0, 0], [100, 0], [100, 100], [0, 100]]
        world = [[0, 0], [200, 0], [200, 200], [0, 200]]  # 2 mm/px
        cal.compute_homography(img, world)
        xw, yw = cal.pixel_to_world(50, 50)
        assert abs(xw - 100) < 1.0
        assert abs(yw - 100) < 1.0
        xr, yr = cal.world_to_robot(xw, yw)
        assert cal.is_reachable(xr, yr, 0)
        rmse = cal.validate_points(img, world)
        assert rmse < 1.0

    def test_outside_workspace(self):
        cal = Mark2Calibration(
            workspace=Mark2WorkspaceSettings(min_radius_mm=10, max_radius_mm=50),
        )
        assert not cal.is_reachable(100, 0, 0)


class TestKinematics:
    def test_ik_reachable(self):
        kin = Mark2Kinematics(
            Mark2GeometrySettings(link_1_mm=100, link_2_mm=100, shoulder_height_mm=100),
            Mark2ServosSettings(),
        )
        # ponto no alcance: r=100, z=100 -> z_rel=0
        angles = kin.inverse(100, 0, 100)
        assert 15 <= angles.base <= 165

    def test_ik_out_of_reach(self):
        kin = Mark2Kinematics(
            Mark2GeometrySettings(link_1_mm=50, link_2_mm=50, shoulder_height_mm=0),
        )
        with pytest.raises(Mark2KinematicsError):
            kin.inverse(200, 0, 0)

    def test_ik_requires_geometry(self):
        kin = Mark2Kinematics(Mark2GeometrySettings(link_1_mm=0, link_2_mm=0))
        with pytest.raises(Mark2KinematicsError):
            kin.inverse(10, 0, 0)


class TestFSMTransitions:
    def test_idle_allows_detecting(self):
        assert RobotState.DETECTING in VALID_TRANSITIONS[RobotState.IDLE]
        assert RobotState.SMOKE_TRIGGER in VALID_TRANSITIONS[RobotState.IDLE]
