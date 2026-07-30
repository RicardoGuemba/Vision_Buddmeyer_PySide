# -*- coding: utf-8 -*-
"""Worker QThread — único escritor da porta serial Mark2."""

from __future__ import annotations

import queue
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from PySide6.QtCore import QThread, Signal

from core.logger import get_logger
from .mark2_serial import Mark2Serial, Mark2SerialError
from .pick_planner import PlanStep, PickPlanner

logger = get_logger("robot.worker")


@dataclass
class RobotTask:
    kind: str  # connect|disconnect|home|move|stop|plan|smoke
    payload: dict = field(default_factory=dict)
    on_done: Optional[Callable[[bool, str], None]] = None


class RobotWorker(QThread):
    """Fila de tarefas serial; não bloqueia a UI."""

    state_message = Signal(str)
    task_finished = Signal(str, bool, str)  # kind, ok, message
    angles_changed = Signal(dict)
    step_progress = Signal(str)
    connected_changed = Signal(bool)

    def __init__(self, serial_client: Optional[Mark2Serial] = None, parent=None) -> None:
        super().__init__(parent)
        self._serial = serial_client or Mark2Serial()
        self._queue: queue.Queue[Optional[RobotTask]] = queue.Queue()
        self._running = True
        self._stop_flag = False

    @property
    def serial(self) -> Mark2Serial:
        return self._serial

    def enqueue(self, task: RobotTask) -> None:
        self._queue.put(task)

    def request_stop(self) -> None:
        self._stop_flag = True
        try:
            self._serial.stop()
        except Exception:
            pass

    def shutdown(self) -> None:
        self._running = False
        self._queue.put(None)
        self.wait(3000)

    def run(self) -> None:
        while self._running:
            try:
                task = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if task is None:
                break
            self._stop_flag = False
            ok = False
            msg = ""
            try:
                ok, msg = self._handle(task)
            except Mark2SerialError as exc:
                ok, msg = False, str(exc)
                logger.error("robot_task_serial_error", error=msg, kind=task.kind)
            except Exception as exc:
                ok, msg = False, str(exc)
                logger.error("robot_task_error", error=msg, kind=task.kind)
            self.task_finished.emit(task.kind, ok, msg)
            if task.on_done:
                try:
                    task.on_done(ok, msg)
                except Exception:
                    pass

    def _handle(self, task: RobotTask) -> tuple[bool, str]:
        kind = task.kind
        p = task.payload
        if kind == "connect":
            resp = self._serial.connect(wait_ready=True)
            self.connected_changed.emit(True)
            self.angles_changed.emit(self._serial.angles)
            return True, resp
        if kind == "disconnect":
            self._serial.disconnect()
            self.connected_changed.emit(False)
            return True, "DISCONNECTED"
        if kind == "home":
            resp = self._serial.home()
            self.angles_changed.emit(self._serial.angles)
            return True, resp
        if kind == "stop":
            resp = self._serial.stop()
            return True, resp
        if kind == "move":
            resp = self._serial.move(
                p["base"], p["shoulder"], p["elbow"], p["gripper"], p.get("speed", 15)
            )
            self.angles_changed.emit(self._serial.angles)
            return True, resp
        if kind == "smoke":
            # Pulso na garra com hold configurável (default 1 s)
            angles = self._serial.angles
            open_g = int(p.get("open", 110))
            closed_g = int(p.get("closed", 60))
            speed = int(p.get("speed", 20))
            hold = float(p.get("hold_seconds", 1.0))
            self.step_progress.emit("Smoke: fechar garra")
            self._serial.move(
                angles["base"], angles["shoulder"], angles["elbow"], closed_g, speed
            )
            # Mantém activo ~1 s (ou hold_seconds)
            t_end = time.monotonic() + max(0.1, hold)
            while time.monotonic() < t_end:
                if self._stop_flag:
                    raise Mark2SerialError("STOPPED")
                time.sleep(0.05)
            self.step_progress.emit("Smoke: abrir garra")
            self._serial.move(
                angles["base"], angles["shoulder"], angles["elbow"], open_g, speed
            )
            self.angles_changed.emit(self._serial.angles)
            return True, "SMOKE_OK"
        if kind == "plan":
            planner: PickPlanner = p["planner"]
            steps = p["steps"]
            def on_step(step: PlanStep) -> None:
                self.step_progress.emit(step.label)
                if self._stop_flag:
                    raise Mark2SerialError("STOPPED")

            planner.execute_steps(
                steps,
                move_fn=self._serial.move,
                home_fn=self._serial.home,
                current_angles=self._serial.angles,
                on_step=on_step,
            )
            self.angles_changed.emit(self._serial.angles)
            return True, "PLAN_OK"
        return False, f"Tarefa desconhecida: {kind}"
