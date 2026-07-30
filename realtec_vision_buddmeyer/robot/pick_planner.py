# -*- coding: utf-8 -*-
"""Planeador de sequência Pick-and-Place Mark2."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, List, Optional, Tuple

from config.settings import Mark2HeightsSettings, Mark2HomeAnglesSettings, Mark2ServosSettings
from .mark2_kinematics import JointAngles, Mark2Kinematics, Mark2KinematicsError


class PlanStepKind(str, Enum):
    HOME = "HOME"
    MOVE = "MOVE"
    OPEN_GRIPPER = "OPEN_GRIPPER"
    CLOSE_GRIPPER = "CLOSE_GRIPPER"


@dataclass
class PlanStep:
    kind: PlanStepKind
    label: str
    angles: Optional[JointAngles] = None
    gripper: Optional[int] = None
    speed: int = 15


class PickPlanner:
    """Gera a sequência de movimentos pick → place → home."""

    def __init__(
        self,
        kinematics: Mark2Kinematics,
        heights: Optional[Mark2HeightsSettings] = None,
        servos: Optional[Mark2ServosSettings] = None,
        home: Optional[Mark2HomeAnglesSettings] = None,
        speed: int = 15,
    ) -> None:
        self.kinematics = kinematics
        self.heights = heights or Mark2HeightsSettings()
        self.servos = servos or Mark2ServosSettings()
        self.home = home or Mark2HomeAnglesSettings()
        self.speed = speed

    def build_pick_place(
        self,
        pick_xyz: Tuple[float, float, float],
        drop_xyz: Optional[Tuple[float, float, float]] = None,
    ) -> List[PlanStep]:
        px, py, pz = pick_xyz
        if drop_xyz is None:
            drop_xyz = (
                self.heights.drop_x_mm,
                self.heights.drop_y_mm,
                self.heights.drop_z_mm,
            )
        dx, dy, dz = drop_xyz
        approach_z = pz + self.heights.approach_offset_mm
        drop_approach_z = dz + self.heights.approach_offset_mm

        try:
            approach = self.kinematics.inverse(px, py, approach_z)
            descend = self.kinematics.inverse(px, py, pz)
            lift = approach
            transport = self.kinematics.inverse(dx, dy, drop_approach_z)
            drop = self.kinematics.inverse(dx, dy, dz)
            drop_lift = transport
        except Mark2KinematicsError:
            raise

        open_g = self.servos.gripper.open
        closed_g = self.servos.gripper.closed
        steps: List[PlanStep] = [
            PlanStep(PlanStepKind.HOME, "HOME", speed=self.speed),
            PlanStep(PlanStepKind.OPEN_GRIPPER, "Abrir garra", gripper=open_g, speed=self.speed),
            PlanStep(PlanStepKind.MOVE, "Aproximar", angles=approach, gripper=open_g, speed=self.speed),
            PlanStep(PlanStepKind.MOVE, "Descer", angles=descend, gripper=open_g, speed=self.speed),
            PlanStep(PlanStepKind.CLOSE_GRIPPER, "Fechar garra", angles=descend, gripper=closed_g, speed=self.speed),
            PlanStep(PlanStepKind.MOVE, "Subir", angles=lift, gripper=closed_g, speed=self.speed),
            PlanStep(PlanStepKind.MOVE, "Transportar", angles=transport, gripper=closed_g, speed=self.speed),
            PlanStep(PlanStepKind.MOVE, "Descer destino", angles=drop, gripper=closed_g, speed=self.speed),
            PlanStep(PlanStepKind.OPEN_GRIPPER, "Abrir garra", angles=drop, gripper=open_g, speed=self.speed),
            PlanStep(PlanStepKind.MOVE, "Subir destino", angles=drop_lift, gripper=open_g, speed=self.speed),
            PlanStep(PlanStepKind.HOME, "Retornar HOME", speed=self.speed),
        ]
        return steps

    def execute_steps(
        self,
        steps: List[PlanStep],
        move_fn: Callable[[int, int, int, int, int], str],
        home_fn: Callable[[], str],
        current_angles: dict,
        on_step: Optional[Callable[[PlanStep], None]] = None,
    ) -> None:
        """Executa passos chamando move/home; propaga excepções do serial."""
        cur = dict(current_angles)
        for step in steps:
            if on_step:
                on_step(step)
            if step.kind == PlanStepKind.HOME:
                home_fn()
                cur.update(
                    {
                        "base": self.home.base,
                        "shoulder": self.home.shoulder,
                        "elbow": self.home.elbow,
                        "gripper": self.home.gripper,
                    }
                )
                continue
            g = step.gripper if step.gripper is not None else cur.get("gripper", self.servos.gripper.open)
            if step.angles is not None:
                b, s, e = step.angles.base, step.angles.shoulder, step.angles.elbow
            else:
                b, s, e = cur["base"], cur["shoulder"], cur["elbow"]
            move_fn(b, s, e, g, step.speed)
            cur.update({"base": b, "shoulder": s, "elbow": e, "gripper": g})
