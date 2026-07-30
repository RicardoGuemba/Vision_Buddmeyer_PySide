# -*- coding: utf-8 -*-
"""Controlador FSM Mark2 — orquestra visão → calibração → planner → worker."""

from __future__ import annotations

import time
from typing import Optional, Tuple

from PySide6.QtCore import QObject, Signal

from config import get_settings
from config.settings import Mark2Settings
from core.logger import get_logger
from detection.events import DetectionResult

from .detected_package import DetectedPackage, detection_to_package
from .detection_stabilizer import DetectionStabilizer, StabilizerConfig
from .mark2_calibration import Mark2Calibration
from .mark2_kinematics import Mark2Kinematics, Mark2KinematicsError
from .mark2_serial import Mark2Serial
from .pick_planner import PickPlanner
from .robot_state import BUSY_STATES, VALID_TRANSITIONS, RobotState
from .robot_worker import RobotTask, RobotWorker

logger = get_logger("robot.controller")


class Mark2Controller(QObject):
    """FSM de alto nível; movimento só via RobotWorker."""

    state_changed = Signal(str)
    status_message = Signal(str)
    package_locked = Signal(object)  # DetectedPackage
    cycle_completed = Signal()
    error_occurred = Signal(str)
    coordinates_updated = Signal(dict)  # px/world/robot/reachable
    angles_changed = Signal(dict)
    connected_changed = Signal(bool)

    def __init__(
        self,
        mark2: Optional[Mark2Settings] = None,
        worker: Optional[RobotWorker] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        settings = get_settings()
        self.mark2 = mark2 or settings.mark2
        self._state = RobotState.DISCONNECTED
        self._mode = self.mark2.operation.mode
        self._locked: Optional[DetectedPackage] = None
        self._last_smoke_ts = 0.0
        self._smoke_last_trigger_point: Optional[Tuple[float, float]] = None

        self.calibration = Mark2Calibration(
            self.mark2.calibration,
            self.mark2.reference,
            self.mark2.workspace,
        )
        self.kinematics = Mark2Kinematics(self.mark2.geometry, self.mark2.servos)
        self.planner = PickPlanner(
            self.kinematics,
            self.mark2.heights,
            self.mark2.servos,
            self.mark2.home_angles,
            speed=self.mark2.operation.default_move_speed,
        )
        gate = self.mark2.detection
        self.stabilizer = DetectionStabilizer(
            StabilizerConfig(
                minimum_confidence=gate.minimum_confidence,
                stable_frames=gate.stable_frames,
                point_tolerance_px=gate.point_tolerance_px,
                maximum_area_variation=gate.maximum_area_variation,
            )
        )
        self.worker = worker or RobotWorker(
            Mark2Serial(
                port=self.mark2.serial.port,
                baudrate=self.mark2.serial.baudrate,
                timeout_seconds=self.mark2.serial.timeout_seconds,
            )
        )
        self.worker.task_finished.connect(self._on_task_finished)
        self.worker.step_progress.connect(self.status_message.emit)
        self.worker.angles_changed.connect(self.angles_changed.emit)
        self.worker.connected_changed.connect(self._on_connected_changed)

    @property
    def state(self) -> RobotState:
        return self._state

    @property
    def is_idle(self) -> bool:
        return self._state == RobotState.IDLE

    @property
    def is_busy(self) -> bool:
        return self._state in BUSY_STATES

    def set_mode(self, mode: str) -> None:
        if mode in ("manual", "semi", "auto"):
            self._mode = mode
            self.mark2.operation.mode = mode

    def start_worker(self) -> None:
        if not self.worker.isRunning():
            self.worker.start()

    def stop_worker(self) -> None:
        self.worker.shutdown()

    def connect_robot(self) -> None:
        self.start_worker()
        # Relê porta/baud do YAML (pode ter mudado na Configuração)
        s = get_settings(reload=True).mark2.serial
        self.mark2.serial = s
        self.worker.serial.port = s.port
        self.worker.serial.baudrate = s.baudrate
        self.worker.serial.timeout_seconds = s.timeout_seconds
        self.worker.enqueue(RobotTask(kind="connect"))

    def disconnect_robot(self) -> None:
        self.worker.enqueue(RobotTask(kind="disconnect"))

    def home(self) -> None:
        if self.is_busy:
            self.status_message.emit("Robô ocupado")
            return
        self._transition(RobotState.RETURNING_HOME)
        self.worker.enqueue(RobotTask(kind="home"))

    def stop(self) -> None:
        self.worker.request_stop()
        self.worker.enqueue(RobotTask(kind="stop"))
        self._transition(RobotState.EMERGENCY_STOP)
        self.status_message.emit("STOP enviado")

    def reset_error(self) -> None:
        if self._state in (RobotState.ERROR, RobotState.EMERGENCY_STOP):
            self._transition(RobotState.IDLE)
            self.stabilizer.reset()
            self._locked = None

    def open_gripper(self) -> None:
        if self.is_busy:
            return
        a = self.worker.serial.angles
        self.worker.enqueue(
            RobotTask(
                kind="move",
                payload={
                    "base": a["base"],
                    "shoulder": a["shoulder"],
                    "elbow": a["elbow"],
                    "gripper": self.mark2.servos.gripper.open,
                    "speed": self.mark2.operation.default_move_speed,
                },
            )
        )

    def close_gripper(self) -> None:
        if self.is_busy:
            return
        a = self.worker.serial.angles
        self.worker.enqueue(
            RobotTask(
                kind="move",
                payload={
                    "base": a["base"],
                    "shoulder": a["shoulder"],
                    "elbow": a["elbow"],
                    "gripper": self.mark2.servos.gripper.closed,
                    "speed": self.mark2.operation.default_move_speed,
                },
            )
        )

    def test_move(self) -> None:
        """Pequeno movimento de teste (base ±10°)."""
        if self.is_busy or self._state == RobotState.DISCONNECTED:
            return
        a = self.worker.serial.angles
        target = min(a["base"] + 10, self.mark2.servos.base.maximum)
        self.worker.enqueue(
            RobotTask(
                kind="move",
                payload={
                    "base": target,
                    "shoulder": a["shoulder"],
                    "elbow": a["elbow"],
                    "gripper": a["gripper"],
                    "speed": self.mark2.operation.default_move_speed,
                },
            )
        )

    def authorize_pick(self) -> None:
        """Operador autoriza pick-and-place (modo semi)."""
        if self._state != RobotState.WAITING_AUTHORIZATION or self._locked is None:
            return
        self._start_pick_place(self._locked)

    def process_detection_result(self, result: DetectionResult) -> None:
        """Consome DetectionResult (com máscaras) do pipeline de visão."""
        if self._state == RobotState.DISCONNECTED:
            return
        if not self.mark2.operation.enabled:
            return

        settings = get_settings()
        # Smoke: limiar de confiança da visão (mais permissivo que pick)
        if self.mark2.operation.smoke_detection_trigger:
            thr = float(settings.detection.confidence_threshold)
            best = result.best_detection
            if best is not None and best.confidence < thr:
                best = None
            package = detection_to_package(best, object_id=0) if best is not None else None
            self._handle_smoke_detection(package)
            return

        if self.is_busy:
            return

        thr = settings.detection.plc_confidence_threshold
        best = result.best_for_plc(threshold=thr)
        package = detection_to_package(best, object_id=0) if best is not None else None

        if self._mode == "manual" and self._state == RobotState.IDLE:
            self._transition(RobotState.DETECTING)

        if self._state not in (
            RobotState.IDLE,
            RobotState.DETECTING,
            RobotState.VALIDATING,
        ):
            return

        if self._state == RobotState.IDLE:
            self._transition(RobotState.DETECTING)

        locked = self.stabilizer.update(package, robot_idle=True)
        if locked is None:
            return

        self._locked = locked
        self.package_locked.emit(locked)
        u, v = locked.pick_point_px
        triple = self.calibration.project(float(u), float(v), self.mark2.heights.package_z_mm)
        self.coordinates_updated.emit(
            {
                "pixel": triple.pixel,
                "world_mm": triple.world_mm,
                "robot_mm": triple.robot_mm,
                "reachable": triple.reachable,
                "message": triple.message,
            }
        )

        self._transition(RobotState.VALIDATING)
        if not triple.reachable or triple.robot_mm is None:
            self.status_message.emit(triple.message or "Não alcançável")
            self._transition(RobotState.IDLE)
            return

        if self._mode == "semi":
            self._transition(RobotState.WAITING_AUTHORIZATION)
            self.status_message.emit("Objecto estável. Autorizar Pick-and-Place.")
            return
        if self._mode == "auto":
            self._start_pick_place(locked)
            return
        # manual: só mostra coords
        self._transition(RobotState.IDLE)
        self.status_message.emit("Objecto estável (modo manual)")

    def _handle_smoke_detection(self, package: Optional[DetectedPackage]) -> None:
        """
        Aciona o motor 1× por ~1 s quando a embalagem faz um *novo movimento*
        (deslocamento do ponto de pega ≥ smoke_movement_tolerance_px desde o
        último disparo). Sem objecto → limpa referência.
        """
        if package is None:
            self._smoke_last_trigger_point = None
            return

        point = (float(package.centroid_px[0]), float(package.centroid_px[1]))
        tol = float(self.mark2.operation.smoke_movement_tolerance_px)
        ref = self._smoke_last_trigger_point
        if ref is None:
            is_new_move = True
        else:
            dist = ((point[0] - ref[0]) ** 2 + (point[1] - ref[1]) ** 2) ** 0.5
            is_new_move = dist >= tol

        if not is_new_move:
            return

        if self.is_busy or self._state not in (RobotState.IDLE, RobotState.DETECTING):
            return

        now = time.monotonic()
        cooldown = float(self.mark2.operation.smoke_cooldown_seconds)
        if now - self._last_smoke_ts < cooldown:
            return

        hold = float(self.mark2.operation.smoke_hold_seconds)
        self._smoke_last_trigger_point = point
        self._last_smoke_ts = now
        self._transition(RobotState.SMOKE_TRIGGER)
        self.status_message.emit(f"Movimento embalagem → motor {hold:.0f}s")
        logger.info(
            "smoke_movement_trigger",
            confidence=package.confidence,
            pick_point=point,
            hold_seconds=hold,
        )
        self.worker.enqueue(
            RobotTask(
                kind="smoke",
                payload={
                    "open": self.mark2.servos.gripper.open,
                    "closed": self.mark2.servos.gripper.closed,
                    "speed": self.mark2.operation.default_move_speed,
                    "hold_seconds": hold,
                },
            )
        )

    def execute_pick_place_locked(self) -> None:
        if self._locked is None:
            self.status_message.emit("Sem objecto bloqueado")
            return
        self._start_pick_place(self._locked)

    def _start_pick_place(self, package: DetectedPackage) -> None:
        u, v = package.pick_point_px
        try:
            xr, yr = self.calibration.pixel_to_robot(float(u), float(v))
        except Exception as exc:
            self._fail(str(exc))
            return
        zr = self.mark2.heights.package_z_mm
        if not self.calibration.is_reachable(xr, yr, zr):
            self._fail("Alvo fora do workspace")
            return
        try:
            steps = self.planner.build_pick_place((xr, yr, zr))
        except Mark2KinematicsError as exc:
            self._fail(str(exc))
            return

        self._transition(RobotState.PLANNING)
        self.status_message.emit("A planear Pick-and-Place…")
        self._transition(RobotState.APPROACHING)
        self.worker.enqueue(
            RobotTask(
                kind="plan",
                payload={"planner": self.planner, "steps": steps},
            )
        )

    def _on_task_finished(self, kind: str, ok: bool, message: str) -> None:
        if kind == "connect":
            if ok:
                self._transition(RobotState.IDLE)
                self.status_message.emit("Mark2 READY")
            else:
                self._transition(RobotState.ERROR)
                self.error_occurred.emit(message)
            return
        if kind == "disconnect":
            self._transition(RobotState.DISCONNECTED)
            return
        if kind == "home":
            self._transition(RobotState.IDLE if ok else RobotState.ERROR)
            if ok:
                self.status_message.emit("HOME OK")
            else:
                self.error_occurred.emit(message)
            return
        if kind == "smoke":
            self._transition(RobotState.IDLE if ok else RobotState.ERROR)
            self.status_message.emit(message)
            return
        if kind == "plan":
            if ok:
                self._transition(RobotState.IDLE)
                self.stabilizer.reset()
                self._locked = None
                self.cycle_completed.emit()
                self.status_message.emit("Pick-and-Place concluído")
            else:
                self._fail(message)
            return
        if kind == "stop":
            self._transition(RobotState.EMERGENCY_STOP)
            return
        if kind == "move":
            if not ok:
                self._fail(message)
            return

    def _on_connected_changed(self, connected: bool) -> None:
        self.connected_changed.emit(connected)
        if not connected and self._state != RobotState.DISCONNECTED:
            self._transition(RobotState.DISCONNECTED)

    def _fail(self, message: str) -> None:
        logger.error("mark2_error", error=message)
        self.error_occurred.emit(message)
        self.status_message.emit(message)
        self._transition(RobotState.ERROR)

    def _transition(self, new_state: RobotState) -> None:
        allowed = VALID_TRANSITIONS.get(self._state, set())
        if new_state != self._state and new_state not in allowed:
            # permitir reset forçado para ERROR/ESTOP
            if new_state not in (RobotState.ERROR, RobotState.EMERGENCY_STOP, RobotState.IDLE):
                logger.warning(
                    "invalid_transition",
                    from_state=self._state.value,
                    to_state=new_state.value,
                )
                return
        self._state = new_state
        self.state_changed.emit(new_state.value)
