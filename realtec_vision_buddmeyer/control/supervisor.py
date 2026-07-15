# -*- coding: utf-8 -*-
"""
Supervisor MVP: seleção de alvo de pick e envio único ao CLP (sem FSM).
"""

from __future__ import annotations

import time
from typing import Callable, Optional, Tuple

from PySide6.QtCore import QObject, Signal

from config import get_settings
from core.logger import get_logger
from detection.events import DetectionEvent, DetectionResult
from preprocessing.roi_manager import clamp_centroid_to_roi

logger = get_logger("control.supervisor")

RoiGetter = Callable[[], Tuple[bool, Optional[list]]]


class VisionSupervisor(QObject):
    """
    Orquestra envio de coordenadas ao CLP no modo MVP.

    Seleciona o alvo via DetectionResult.best_for_plc (área aparente + confiança),
    aplica clamp ROI, converte px→mm e escreve tags CIP.
    """

    pick_sent = Signal(object)
    pick_skipped = Signal(str)

    def __init__(self, cip_client, settings=None, parent=None):
        super().__init__(parent)
        self._cip_client = cip_client
        self._settings = settings or get_settings()
        self._roi_getter: Optional[RoiGetter] = None
        self._last_send_monotonic = 0.0
        self._min_send_interval_s = 1.0 / max(
            1, int(self._settings.detection.inference_fps)
        )

    def set_roi_getter(self, getter: RoiGetter) -> None:
        self._roi_getter = getter

    @property
    def plc_threshold(self) -> float:
        return float(self._settings.detection.plc_confidence_threshold)

    def pick_target_from_result(self, result: DetectionResult):
        """Retorna a Detection escolhida para pick ou None."""
        return result.best_for_plc(threshold=self.plc_threshold)

    def build_plc_payload(
        self,
        result: DetectionResult,
    ) -> Optional[dict]:
        """Monta valores em mm prontos para write_detection_result."""
        detection = self.pick_target_from_result(result)
        if detection is None:
            return None

        centroid_x_px, centroid_y_px = detection.centroid
        roi_enabled, roi_coords = (False, None)
        if self._roi_getter is not None:
            roi_enabled, roi_coords = self._roi_getter()
        if roi_enabled and roi_coords and len(roi_coords) == 4:
            centroid_x_px, centroid_y_px = clamp_centroid_to_roi(
                centroid_x_px, centroid_y_px, tuple(roi_coords)
            )

        mm_per_px = getattr(
            self._settings.preprocess, "roi_calibration_mm_per_px", 1.0
        ) or 1.0
        area_px = float(detection.area_px or 0.0)
        return {
            "detected": True,
            "centroid_x": centroid_x_px * mm_per_px,
            "centroid_y": centroid_y_px * mm_per_px,
            "confidence": float(detection.confidence),
            "detection_count": len(result.visible_detections(self.plc_threshold)),
            "processing_time": float(result.inference_time_ms),
            "angle_deg": float(detection.angle_deg or 0.0),
            "area": area_px * (mm_per_px ** 2),
        }

    async def send_pick_target(self, result: DetectionResult) -> bool:
        """Envia alvo de pick ao CLP. Retorna True se enviou."""
        if not self._cip_client._state.is_connected:
            logger.debug("supervisor_skip_not_connected")
            return False
        if self._cip_client._state.status.value == "degraded":
            logger.debug("supervisor_skip_degraded")
            return False

        payload = self.build_plc_payload(result)
        if payload is None:
            return False

        try:
            robot_ready = True
            try:
                robot_ready = await self._cip_client.read_tag("RobotReady")
            except Exception:
                pass
            if not robot_ready:
                logger.debug("supervisor_skip_robot_not_ready")
                return False

            await self._cip_client.write_detection_result(**payload)
            self._last_send_monotonic = time.monotonic()
            event = DetectionEvent.from_result(
                result,
                plc_threshold=self.plc_threshold,
            )
            self.pick_sent.emit(event)
            logger.info(
                "supervisor_pick_sent",
                centroid_x=payload["centroid_x"],
                centroid_y=payload["centroid_y"],
                angle_deg=payload["angle_deg"],
                area_mm2=payload["area"],
                confidence=payload["confidence"],
            )
            return True
        except Exception as exc:
            logger.warning("supervisor_send_failed", error=str(exc))
            self.pick_skipped.emit(str(exc))
            return False

    def handle_detection_result(self, result: DetectionResult) -> None:
        """Chamado na GUI thread após inferência; respeita rate-limit."""
        if self.pick_target_from_result(result) is None:
            return
        now = time.monotonic()
        if now - self._last_send_monotonic < self._min_send_interval_s:
            return
        import asyncio

        asyncio.create_task(self.send_pick_target(result))
