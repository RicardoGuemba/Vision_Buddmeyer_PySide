# -*- coding: utf-8 -*-
"""
Pós-processamento de instance segmentation (Mask2Former / DETR-style).

Responsabilidades:
- Chamar o `post_process_instance_segmentation` do Mask2FormerImageProcessor
  com `target_sizes` no referencial do frame original.
- Filtrar segmentos por confiança e classe-alvo.
- Para cada instância: extrair máscara binária (H_frame, W_frame), calcular
  centróide/ângulo/área via `mask_geometry.compute_mask_geometry` e
  construir o dataclass `Detection` com bbox (a partir da máscara).

O objetivo é manter o contrato do pipeline original (DetectionResult)
exatamente igual, apenas enriquecido com `mask`, `angle_deg` e `area_px`,
para que o resto do sistema (UI, CLP, controle do robô) possa consumir
opcionalmente essas informações.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import torch

from core.logger import get_logger

from .events import BoundingBox, Detection, DetectionResult
from .mask_geometry import compute_mask_geometry


logger = get_logger("detection.seg_post")


class SegmentationPostProcessor:
    """
    Pós-processador para modelos Mask2Former (instance segmentation).

    Compatível em "duck type" com PostProcessor:
      - `process(outputs, target_sizes, id2label, frame_id, inference_time_ms) -> DetectionResult`
      - setters `set_confidence_threshold`, `set_max_detections`, `set_target_classes`

    Args:
        processor: Mask2FormerImageProcessor (do `AutoImageProcessor`).
        confidence_threshold: score mínimo para aceitar um segmento.
        max_detections: número máximo de detecções a retornar.
        target_classes: lista de class_names aceitos (None = todas).
        min_mask_pixels: descarta máscaras menores que este número de pixels
            (evita ruído e previne NaN no cálculo do PCA).
        mask_threshold: threshold interno do Mask2Former para binarizar masks.
        overlap_mask_area_threshold: threshold de sobreposição de masks
            (ver docs do transformers).
    """

    def __init__(
        self,
        processor: Any,
        confidence_threshold: float = 0.5,
        max_detections: int = 10,
        target_classes: Optional[List[str]] = None,
        min_mask_pixels: int = 64,
        mask_threshold: float = 0.5,
        overlap_mask_area_threshold: float = 0.8,
    ):
        self._processor = processor
        self.confidence_threshold = float(confidence_threshold)
        self.max_detections = int(max_detections)
        self.target_classes = target_classes
        self.min_mask_pixels = int(min_mask_pixels)
        self.mask_threshold = float(mask_threshold)
        self.overlap_mask_area_threshold = float(overlap_mask_area_threshold)

    def process(
        self,
        outputs: Any,
        target_sizes: torch.Tensor,
        id2label: Dict[int, str],
        frame_id: int = 0,
        inference_time_ms: float = 0.0,
    ) -> DetectionResult:
        """
        Converte a saída crua do Mask2Former em DetectionResult.

        target_sizes: tensor [[H_frame, W_frame]] no referencial da imagem
            original (não do input do modelo). O processor redimensiona
            as máscaras para esse tamanho.
        """
        # Diagnóstico cru: maior probabilidade de classe "real" entre todas
        # as queries (independente do threshold). Permite saber, mesmo quando
        # nenhuma detecção é emitida, se o modelo está "vendo" algo.
        max_query_score = self._compute_max_query_score(outputs)

        # Normaliza id2label para chaves int — defensivo contra configs
        # carregados do JSON com chaves string ("0" -> "Embalagem").
        id2label_norm = self._normalize_id2label(id2label)

        try:
            target_sizes_list = target_sizes.tolist() if hasattr(target_sizes, "tolist") else target_sizes

            results = self._processor.post_process_instance_segmentation(
                outputs,
                threshold=self.confidence_threshold,
                mask_threshold=self.mask_threshold,
                overlap_mask_area_threshold=self.overlap_mask_area_threshold,
                target_sizes=target_sizes_list,
                return_binary_maps=True,
            )
        except Exception as exc:
            logger.error("seg_postprocess_failed", error=str(exc))
            return DetectionResult(
                detections=[],
                inference_time_ms=inference_time_ms,
                frame_id=frame_id,
                max_query_score=max_query_score,
            )

        if not results:
            return DetectionResult(
                detections=[],
                inference_time_ms=inference_time_ms,
                frame_id=frame_id,
                max_query_score=max_query_score,
            )

        result = results[0]

        segmentation: Optional[torch.Tensor] = result.get("segmentation")
        segments_info: List[Dict[str, Any]] = result.get("segments_info", []) or []
        raw_segment_count = len(segments_info)

        if segmentation is None or not segments_info:
            return DetectionResult(
                detections=[],
                inference_time_ms=inference_time_ms,
                frame_id=frame_id,
                max_query_score=max_query_score,
                raw_segment_count=raw_segment_count,
            )

        seg_np = segmentation.detach().cpu().numpy() if isinstance(segmentation, torch.Tensor) else np.asarray(segmentation)

        binary_maps: Optional[np.ndarray] = None
        if seg_np.ndim == 3:
            binary_maps = seg_np.astype(bool)

        detections: List[Detection] = []
        rejected_by_class = 0

        candidates = sorted(
            segments_info,
            key=lambda s: float(s.get("score", 0.0)),
            reverse=True,
        )

        for seg in candidates:
            score = float(seg.get("score", 0.0))
            if score < self.confidence_threshold:
                continue

            label_id = int(seg.get("label_id", -1))
            class_name = id2label_norm.get(label_id, f"class_{label_id}")

            if self.target_classes and class_name not in self.target_classes:
                rejected_by_class += 1
                continue

            mask = self._extract_mask_for_segment(seg, seg_np, binary_maps)
            if mask is None:
                continue

            geometry = compute_mask_geometry(mask, min_pixels=self.min_mask_pixels)
            if geometry is None:
                continue

            bbox = self._bbox_from_mask(mask)
            if bbox is None:
                continue

            detection = Detection(
                bbox=bbox,
                confidence=score,
                class_id=label_id,
                class_name=class_name,
                mask=mask,
                centroid_override=(geometry.centroid_x, geometry.centroid_y),
                angle_deg=float(geometry.angle_deg),
                area_px=float(geometry.area_px),
                major_axis_length=float(geometry.major_axis_length),
                minor_axis_length=float(geometry.minor_axis_length),
            )
            detections.append(detection)

            if len(detections) >= self.max_detections:
                break

        # Aviso para o operador: o modelo emitiu segmentos acima do threshold
        # mas todos foram rejeitados pela whitelist de classes. Sintoma
        # clássico de target_classes desalinhada com id2label do checkpoint.
        if not detections and rejected_by_class > 0:
            logger.warning(
                "all_segments_rejected_by_class_filter",
                rejected=rejected_by_class,
                target_classes=self.target_classes,
                id2label=dict(list(id2label_norm.items())[:10]),
            )

        return DetectionResult(
            detections=detections,
            inference_time_ms=inference_time_ms,
            frame_id=frame_id,
            max_query_score=max_query_score,
            rejected_by_class=rejected_by_class,
            raw_segment_count=raw_segment_count,
        )

    @staticmethod
    def _normalize_id2label(id2label: Optional[Dict[Any, str]]) -> Dict[int, str]:
        """Garante chaves inteiras em id2label (HF carrega de JSON com str)."""
        if not id2label:
            return {}
        normalized: Dict[int, str] = {}
        for k, v in id2label.items():
            try:
                normalized[int(k)] = str(v)
            except (TypeError, ValueError):
                continue
        return normalized

    @staticmethod
    def _compute_max_query_score(outputs: Any) -> Optional[float]:
        """
        Calcula a maior probabilidade de classe (softmax sobre classes
        reais, ignorando "no object") entre todas as queries do batch.

        Retorna None se os logits não estiverem disponíveis na saída.
        """
        try:
            class_logits = getattr(outputs, "class_queries_logits", None)
            if class_logits is None:
                # Fallback: object detection clássico
                class_logits = getattr(outputs, "logits", None)
            if class_logits is None or not isinstance(class_logits, torch.Tensor):
                return None
            if class_logits.numel() == 0:
                return None
            with torch.no_grad():
                probs = class_logits.softmax(dim=-1)
                # Última coluna = "no object". Pegamos só classes reais.
                real_class_probs = probs[..., :-1]
                if real_class_probs.numel() == 0:
                    return None
                return float(real_class_probs.max().item())
        except Exception:
            return None

    def _extract_mask_for_segment(
        self,
        segment: Dict[str, Any],
        segmentation: np.ndarray,
        binary_maps: Optional[np.ndarray],
    ) -> Optional[np.ndarray]:
        """
        Retorna a máscara binária (H, W) da instância descrita por `segment`.

        Mask2Former retorna ou:
          - segmentation 2D (H, W) com ids das instâncias + segments_info
          - binary_maps 3D (N, H, W) quando `return_binary_maps=True`
        """
        seg_id = int(segment.get("id", -1))

        if binary_maps is not None:
            if 0 <= seg_id < binary_maps.shape[0]:
                return binary_maps[seg_id].astype(bool)
            return None

        if segmentation.ndim == 2:
            return (segmentation == seg_id)

        return None

    @staticmethod
    def _bbox_from_mask(mask: np.ndarray) -> Optional[BoundingBox]:
        """Calcula bbox axis-aligned a partir da máscara binária."""
        ys, xs = np.nonzero(mask)
        if xs.size == 0 or ys.size == 0:
            return None
        x1 = float(xs.min())
        y1 = float(ys.min())
        x2 = float(xs.max()) + 1.0
        y2 = float(ys.max()) + 1.0
        return BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2)

    def set_confidence_threshold(self, threshold: float) -> None:
        self.confidence_threshold = max(0.0, min(1.0, float(threshold)))

    def set_max_detections(self, max_detections: int) -> None:
        self.max_detections = max(1, int(max_detections))

    def set_target_classes(self, classes: Optional[List[str]]) -> None:
        self.target_classes = classes
