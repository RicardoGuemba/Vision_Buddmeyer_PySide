# -*- coding: utf-8 -*-
"""
Testes unitários de detection.segmentation_postprocess.

Usa um processor e outputs "fake" para isolar a lógica do pós-processador
sem depender de pesos ou de transformers em runtime.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _FakeProcessor:
    """Processor fake que devolve um resultado determinístico para testes."""

    def __init__(self, segmentation_map: np.ndarray, segments_info, binary_maps=None):
        import torch

        self._segmentation = torch.from_numpy(segmentation_map)
        self._segments_info = segments_info
        self._binary_maps = torch.from_numpy(binary_maps) if binary_maps is not None else None

    def post_process_instance_segmentation(self, outputs, **kwargs):
        if self._binary_maps is not None:
            return [
                {
                    "segmentation": self._binary_maps,
                    "segments_info": self._segments_info,
                }
            ]
        return [
            {
                "segmentation": self._segmentation,
                "segments_info": self._segments_info,
            }
        ]


def _make_rect_mask(h, w, x, y, rw, rh):
    mask = np.zeros((h, w), dtype=np.uint8)
    mask[y : y + rh, x : x + rw] = 1
    return mask


class TestSegmentationPostProcessor:
    def test_filters_low_confidence(self):
        import torch  # noqa: F401
        from detection.segmentation_postprocess import SegmentationPostProcessor

        seg = np.zeros((40, 40), dtype=np.int32)
        seg[5:35, 5:35] = 0
        binary = np.stack([_make_rect_mask(40, 40, 5, 5, 30, 30)])
        info = [{"id": 0, "label_id": 0, "score": 0.3, "was_fused": False}]

        pp = SegmentationPostProcessor(
            processor=_FakeProcessor(seg, info, binary_maps=binary),
            confidence_threshold=0.5,
            min_mask_pixels=10,
        )
        result = pp.process(
            outputs=SimpleNamespace(),
            target_sizes=SimpleNamespace(tolist=lambda: [[40, 40]]),
            id2label={0: "Embalagem"},
        )
        assert result.count == 0

    def test_filters_by_target_class(self):
        import torch  # noqa: F401
        from detection.segmentation_postprocess import SegmentationPostProcessor

        binary = np.stack([_make_rect_mask(40, 40, 5, 5, 30, 30)])
        info = [{"id": 0, "label_id": 0, "score": 0.9, "was_fused": False}]
        pp = SegmentationPostProcessor(
            processor=_FakeProcessor(np.zeros((40, 40)), info, binary_maps=binary),
            confidence_threshold=0.1,
            target_classes=["Outra"],
            min_mask_pixels=10,
        )
        result = pp.process(
            outputs=SimpleNamespace(),
            target_sizes=SimpleNamespace(tolist=lambda: [[40, 40]]),
            id2label={0: "Embalagem"},
        )
        assert result.count == 0

    def test_builds_detection_with_mask_centroid_angle_area(self):
        import torch  # noqa: F401
        from detection.segmentation_postprocess import SegmentationPostProcessor

        binary = np.stack([_make_rect_mask(100, 200, 10, 40, 180, 20)])
        info = [{"id": 0, "label_id": 0, "score": 0.92, "was_fused": False}]
        pp = SegmentationPostProcessor(
            processor=_FakeProcessor(np.zeros((100, 200)), info, binary_maps=binary),
            confidence_threshold=0.1,
            min_mask_pixels=50,
        )
        result = pp.process(
            outputs=SimpleNamespace(),
            target_sizes=SimpleNamespace(tolist=lambda: [[100, 200]]),
            id2label={0: "Embalagem"},
        )
        assert result.count == 1
        det = result.detections[0]
        assert det.class_name == "Embalagem"
        assert det.has_mask is True
        assert det.mask.shape == (100, 200)
        assert det.area_px is not None and det.area_px > 0
        assert det.angle_deg is not None
        assert 0.0 <= det.angle_deg < 180.0
        assert abs(det.angle_deg) < 5.0 or abs(det.angle_deg - 180.0) < 5.0
        assert det.bbox.x1 == pytest.approx(10.0, abs=1.0)
        assert det.bbox.y1 == pytest.approx(40.0, abs=1.0)

    def test_respects_max_detections(self):
        import torch  # noqa: F401
        from detection.segmentation_postprocess import SegmentationPostProcessor

        masks = np.stack(
            [
                _make_rect_mask(100, 100, 5, 5, 30, 30),
                _make_rect_mask(100, 100, 40, 5, 30, 30),
                _make_rect_mask(100, 100, 5, 40, 30, 30),
                _make_rect_mask(100, 100, 40, 40, 30, 30),
            ]
        )
        info = [
            {"id": i, "label_id": 0, "score": 0.9 - i * 0.05, "was_fused": False}
            for i in range(4)
        ]
        pp = SegmentationPostProcessor(
            processor=_FakeProcessor(np.zeros((100, 100)), info, binary_maps=masks),
            confidence_threshold=0.1,
            max_detections=2,
            min_mask_pixels=10,
        )
        result = pp.process(
            outputs=SimpleNamespace(),
            target_sizes=SimpleNamespace(tolist=lambda: [[100, 100]]),
            id2label={0: "Embalagem"},
        )
        assert result.count == 2

    def test_id2label_normalizes_string_keys(self):
        """
        Defensivo: id2label carregado de JSON pode vir com chaves string
        ("0" -> "Embalagem"); o pós-processador precisa tratar isso, caso
        contrário o filtro de target_classes silenciosamente descarta tudo.
        """
        import torch  # noqa: F401
        from detection.segmentation_postprocess import SegmentationPostProcessor

        binary = np.stack([_make_rect_mask(40, 40, 5, 5, 30, 30)])
        info = [{"id": 0, "label_id": 0, "score": 0.9, "was_fused": False}]
        pp = SegmentationPostProcessor(
            processor=_FakeProcessor(np.zeros((40, 40)), info, binary_maps=binary),
            confidence_threshold=0.1,
            target_classes=["Embalagem"],
            min_mask_pixels=10,
        )
        result = pp.process(
            outputs=SimpleNamespace(),
            target_sizes=SimpleNamespace(tolist=lambda: [[40, 40]]),
            id2label={"0": "Embalagem"},  # chaves string (formato JSON)
        )
        assert result.count == 1
        assert result.detections[0].class_name == "Embalagem"

    def test_diagnostic_fields_populated_when_no_detection(self):
        """
        Quando o threshold descarta tudo, o resultado ainda deve trazer
        max_query_score (calculado a partir dos logits) e raw_segment_count
        para diagnóstico, evitando falha silenciosa no campo.
        """
        import torch
        from detection.segmentation_postprocess import SegmentationPostProcessor

        binary = np.stack([_make_rect_mask(40, 40, 5, 5, 30, 30)])
        # Score 0.4 < threshold 0.7 -> sem detecções
        info = [{"id": 0, "label_id": 0, "score": 0.4, "was_fused": False}]

        # Simula outputs do Mask2Former com class_queries_logits
        # 3 queries, 2 classes (1 real + "no object"); a query 1 tem
        # logit forte para a classe real -> max_query_score ~ alto.
        class_logits = torch.tensor([[
            [0.5, 5.0],   # softmax([..., -1]) classe real ~ 0.011
            [3.0, 0.1],   # classe real ~ 0.95
            [0.0, 0.0],   # classe real = 0.5
        ]])
        outputs = SimpleNamespace(class_queries_logits=class_logits)

        pp = SegmentationPostProcessor(
            processor=_FakeProcessor(np.zeros((40, 40)), info, binary_maps=binary),
            confidence_threshold=0.7,
            target_classes=["Embalagem"],
            min_mask_pixels=10,
        )
        result = pp.process(
            outputs=outputs,
            target_sizes=SimpleNamespace(tolist=lambda: [[40, 40]]),
            id2label={0: "Embalagem"},
        )
        assert result.count == 0
        assert result.max_query_score is not None
        assert 0.9 < result.max_query_score <= 1.0

    def test_rejected_by_class_counter(self):
        """
        Se segmentos passam o threshold mas nenhum bate target_classes,
        rejected_by_class deve ser > 0 (sinaliza desalinhamento de classes).
        """
        import torch  # noqa: F401
        from detection.segmentation_postprocess import SegmentationPostProcessor

        masks = np.stack(
            [
                _make_rect_mask(40, 40, 5, 5, 30, 30),
                _make_rect_mask(40, 40, 5, 5, 30, 30),
            ]
        )
        info = [
            {"id": 0, "label_id": 0, "score": 0.9, "was_fused": False},
            {"id": 1, "label_id": 0, "score": 0.85, "was_fused": False},
        ]
        pp = SegmentationPostProcessor(
            processor=_FakeProcessor(np.zeros((40, 40)), info, binary_maps=masks),
            confidence_threshold=0.5,
            target_classes=["NaoExiste"],
            min_mask_pixels=10,
        )
        result = pp.process(
            outputs=SimpleNamespace(),
            target_sizes=SimpleNamespace(tolist=lambda: [[40, 40]]),
            id2label={0: "Embalagem"},
        )
        assert result.count == 0
        assert result.rejected_by_class == 2
        assert result.raw_segment_count == 2
