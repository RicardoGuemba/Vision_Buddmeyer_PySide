# -*- coding: utf-8 -*-
"""Pacote de integração Mark2 + Arduino."""

from .detected_package import DetectedPackage, calculate_safe_pick_point, detection_to_package
from .detection_stabilizer import DetectionStabilizer, StabilizerConfig
from .mark2_calibration import Mark2Calibration, CoordinateTriple
from .mark2_controller import Mark2Controller
from .mark2_kinematics import Mark2Kinematics, Mark2KinematicsError, JointAngles
from .mark2_serial import Mark2Serial, Mark2SerialError
from .pick_planner import PickPlanner, PlanStep, PlanStepKind
from .robot_state import RobotState
from .robot_worker import RobotWorker, RobotTask

__all__ = [
    "DetectedPackage",
    "calculate_safe_pick_point",
    "detection_to_package",
    "DetectionStabilizer",
    "StabilizerConfig",
    "Mark2Calibration",
    "CoordinateTriple",
    "Mark2Controller",
    "Mark2Kinematics",
    "Mark2KinematicsError",
    "JointAngles",
    "Mark2Serial",
    "Mark2SerialError",
    "PickPlanner",
    "PlanStep",
    "PlanStepKind",
    "RobotState",
    "RobotWorker",
    "RobotTask",
]
