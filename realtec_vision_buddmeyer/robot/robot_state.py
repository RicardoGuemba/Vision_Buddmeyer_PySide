# -*- coding: utf-8 -*-
"""Estados da máquina Mark2."""

from __future__ import annotations

from enum import Enum


class RobotState(str, Enum):
    DISCONNECTED = "DISCONNECTED"
    IDLE = "IDLE"
    DETECTING = "DETECTING"
    VALIDATING = "VALIDATING"
    PLANNING = "PLANNING"
    APPROACHING = "APPROACHING"
    DESCENDING = "DESCENDING"
    GRASPING = "GRASPING"
    LIFTING = "LIFTING"
    TRANSPORTING = "TRANSPORTING"
    RELEASING = "RELEASING"
    RETURNING_HOME = "RETURNING_HOME"
    ERROR = "ERROR"
    EMERGENCY_STOP = "EMERGENCY_STOP"
    WAITING_AUTHORIZATION = "WAITING_AUTHORIZATION"
    SMOKE_TRIGGER = "SMOKE_TRIGGER"


VALID_TRANSITIONS = {
    RobotState.DISCONNECTED: {RobotState.IDLE, RobotState.ERROR},
    RobotState.IDLE: {
        RobotState.DETECTING,
        RobotState.WAITING_AUTHORIZATION,
        RobotState.PLANNING,
        RobotState.SMOKE_TRIGGER,
        RobotState.RETURNING_HOME,
        RobotState.EMERGENCY_STOP,
        RobotState.DISCONNECTED,
        RobotState.ERROR,
    },
    RobotState.DETECTING: {
        RobotState.VALIDATING,
        RobotState.IDLE,
        RobotState.WAITING_AUTHORIZATION,
        RobotState.SMOKE_TRIGGER,
        RobotState.EMERGENCY_STOP,
        RobotState.ERROR,
    },
    RobotState.VALIDATING: {
        RobotState.WAITING_AUTHORIZATION,
        RobotState.PLANNING,
        RobotState.IDLE,
        RobotState.ERROR,
        RobotState.EMERGENCY_STOP,
    },
    RobotState.WAITING_AUTHORIZATION: {
        RobotState.PLANNING,
        RobotState.IDLE,
        RobotState.ERROR,
        RobotState.EMERGENCY_STOP,
    },
    RobotState.PLANNING: {
        RobotState.APPROACHING,
        RobotState.ERROR,
        RobotState.EMERGENCY_STOP,
        RobotState.IDLE,
    },
    RobotState.APPROACHING: {
        RobotState.DESCENDING,
        RobotState.ERROR,
        RobotState.EMERGENCY_STOP,
    },
    RobotState.DESCENDING: {
        RobotState.GRASPING,
        RobotState.ERROR,
        RobotState.EMERGENCY_STOP,
    },
    RobotState.GRASPING: {
        RobotState.LIFTING,
        RobotState.ERROR,
        RobotState.EMERGENCY_STOP,
    },
    RobotState.LIFTING: {
        RobotState.TRANSPORTING,
        RobotState.ERROR,
        RobotState.EMERGENCY_STOP,
    },
    RobotState.TRANSPORTING: {
        RobotState.RELEASING,
        RobotState.ERROR,
        RobotState.EMERGENCY_STOP,
    },
    RobotState.RELEASING: {
        RobotState.RETURNING_HOME,
        RobotState.ERROR,
        RobotState.EMERGENCY_STOP,
    },
    RobotState.RETURNING_HOME: {
        RobotState.IDLE,
        RobotState.ERROR,
        RobotState.EMERGENCY_STOP,
    },
    RobotState.SMOKE_TRIGGER: {
        RobotState.IDLE,
        RobotState.ERROR,
        RobotState.EMERGENCY_STOP,
    },
    RobotState.ERROR: {
        RobotState.IDLE,
        RobotState.DISCONNECTED,
        RobotState.EMERGENCY_STOP,
    },
    RobotState.EMERGENCY_STOP: {
        RobotState.IDLE,
        RobotState.DISCONNECTED,
        RobotState.ERROR,
    },
}


BUSY_STATES = {
    RobotState.PLANNING,
    RobotState.APPROACHING,
    RobotState.DESCENDING,
    RobotState.GRASPING,
    RobotState.LIFTING,
    RobotState.TRANSPORTING,
    RobotState.RELEASING,
    RobotState.RETURNING_HOME,
    RobotState.SMOKE_TRIGGER,
}
