# -*- coding: utf-8 -*-
"""Testes dos campos de segmentação em detection.events."""

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _make_detection(confidence: float, area_px: float, angle_deg: float = 30.0):
    from detection.events import BoundingBox, Detection

    return Detection(
        bbox=BoundingBox(0, 0, 50, 50),
        confidence=confidence,
        class_id=0,
        class_name="Embalagem",
        mask=np.ones((50, 50), dtype=bool),
        centroid_override=(25.0, 25.0),
        angle_deg=angle_deg,
        area_px=area_px,
    )


class TestDetectionSegmentationFields:
    def test_centroid_uses_override(self):
        d = _make_detection(confidence=0.9, area_px=1000.0)
        assert d.centroid == (25.0, 25.0)

    def test_has_mask_and_orientation_true(self):
        d = _make_detection(confidence=0.9, area_px=1000.0)
        assert d.has_mask is True
        assert d.has_orientation is True

    def test_effective_area_prefers_mask(self):
        d = _make_detection(confidence=0.9, area_px=250.0)
        assert d.effective_area_px == 250.0

    def test_effective_area_falls_back_to_bbox(self):
        from detection.events import BoundingBox, Detection

        d = Detection(
            bbox=BoundingBox(0, 0, 10, 20),
            confidence=0.5,
            class_id=0,
            class_name="Embalagem",
        )
        assert d.effective_area_px == 200.0


class TestDetectionResultPriority:
    def test_best_by_priority_prefers_conf_plus_area(self):
        from detection.events import DetectionResult

        low_conf_big = _make_detection(confidence=0.6, area_px=10000.0)
        high_conf_tiny = _make_detection(confidence=0.95, area_px=200.0)
        result = DetectionResult(detections=[low_conf_big, high_conf_tiny])
        best = result.best_by_priority(confidence_weight=1.0, area_weight=1.0)
        assert best is low_conf_big

    def test_best_by_priority_favors_confidence_when_area_weight_zero(self):
        from detection.events import DetectionResult

        low_conf_big = _make_detection(confidence=0.6, area_px=10000.0)
        high_conf_tiny = _make_detection(confidence=0.95, area_px=200.0)
        result = DetectionResult(detections=[low_conf_big, high_conf_tiny])
        best = result.best_by_priority(confidence_weight=1.0, area_weight=0.0)
        assert best is high_conf_tiny

    def test_best_by_priority_returns_none_when_empty(self):
        from detection.events import DetectionResult

        assert DetectionResult().best_by_priority() is None


class TestDetectionEventPlcData:
    def test_from_result_with_prioritization(self):
        from detection.events import DetectionResult, DetectionEvent

        low_conf_big = _make_detection(confidence=0.6, area_px=10000.0, angle_deg=42.0)
        high_conf_tiny = _make_detection(confidence=0.95, area_px=200.0, angle_deg=10.0)
        result = DetectionResult(detections=[low_conf_big, high_conf_tiny])
        ev = DetectionEvent.from_result(result, prioritize_area=True)
        assert ev.detected is True
        assert ev.angle_deg == 42.0
        assert ev.area_px == 10000.0

    def test_to_plc_data_defaults_zero_when_missing(self):
        from detection.events import DetectionResult, DetectionEvent, BoundingBox, Detection

        d = Detection(
            bbox=BoundingBox(0, 0, 10, 10),
            confidence=0.8,
            class_id=0,
            class_name="Embalagem",
        )
        result = DetectionResult(detections=[d])
        ev = DetectionEvent.from_result(result)
        data = ev.to_plc_data()
        assert data["angle_deg"] == 0.0
        assert data["area_px"] == 0.0
        assert data["product_detected"] is True
