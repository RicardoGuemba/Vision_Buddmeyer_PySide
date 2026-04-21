# -*- coding: utf-8 -*-
"""
Dataclasses para eventos de detecção.

Modelo de dados do pipeline de detecção baseado em instance segmentation
(Mask2Former / RT-DETR-style segmentation). Cada detecção carrega, além
do bbox e score:

- mask            : máscara binária (H x W) no referencial do frame original
- centroid        : centroide geométrico da máscara (se disponível), senão centro do bbox
- angle_deg       : ângulo do eixo maior da embalagem em [0, 180) graus
                    (referencial: eixo X da imagem, sentido horário por causa
                    do Y invertido — convenção de imagem)
- area_px         : área da máscara em pixels²

Esses campos dão ao CLP os três elementos que a plataforma de pick
espera: X, Y e Ângulo, mais um proxy de tamanho (área) para priorização.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple, Dict, Any

import numpy as np


@dataclass
class BoundingBox:
    """Bounding box de uma detecção (axis-aligned)."""

    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def center(self) -> Tuple[float, float]:
        """Retorna centro geométrico do bbox."""
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    @property
    def width(self) -> float:
        return abs(self.x2 - self.x1)

    @property
    def height(self) -> float:
        return abs(self.y2 - self.y1)

    @property
    def area(self) -> float:
        return self.width * self.height

    def to_list(self) -> List[float]:
        return [self.x1, self.y1, self.x2, self.y2]

    def to_xywh(self) -> List[float]:
        return [self.x1, self.y1, self.width, self.height]

    @classmethod
    def from_list(cls, bbox: List[float]) -> "BoundingBox":
        return cls(x1=bbox[0], y1=bbox[1], x2=bbox[2], y2=bbox[3])

    @classmethod
    def from_xywh(cls, x: float, y: float, w: float, h: float) -> "BoundingBox":
        return cls(x1=x, y1=y, x2=x + w, y2=y + h)


@dataclass
class Detection:
    """
    Uma detecção individual.

    Com máscara (modelo de segmentação):
        - `centroid` é o centroide geométrico da máscara binária
        - `angle_deg` é o ângulo do eixo maior (PCA da máscara)
        - `area_px` é a área em pixels²

    Sem máscara (modelo de object detection clássico):
        - `centroid` cai no centro do bbox
        - `angle_deg` e `area_px` ficam None
    """

    bbox: BoundingBox
    confidence: float
    class_id: int
    class_name: str

    # Campos opcionais (pipeline de segmentação)
    mask: Optional[np.ndarray] = None            # bool/uint8 (H, W)
    centroid_override: Optional[Tuple[float, float]] = None
    angle_deg: Optional[float] = None            # [0, 180)
    area_px: Optional[float] = None              # pixels²
    major_axis_length: Optional[float] = None    # px (lado maior do retângulo)
    minor_axis_length: Optional[float] = None    # px (lado menor do retângulo)

    @property
    def centroid(self) -> Tuple[float, float]:
        """Centroide geométrico da máscara, ou centro do bbox como fallback."""
        if self.centroid_override is not None:
            return self.centroid_override
        return self.bbox.center

    @property
    def centroid_x(self) -> float:
        return self.centroid[0]

    @property
    def centroid_y(self) -> float:
        return self.centroid[1]

    @property
    def has_mask(self) -> bool:
        return self.mask is not None

    @property
    def has_orientation(self) -> bool:
        return self.angle_deg is not None

    @property
    def effective_area_px(self) -> float:
        """
        Área efetiva em px² preferindo máscara; fallback para bbox.
        Usado em critérios de priorização (robustez quando área da máscara for 0).
        """
        if self.area_px is not None and self.area_px > 0:
            return float(self.area_px)
        return float(self.bbox.area)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "bbox": self.bbox.to_list(),
            "confidence": self.confidence,
            "class_id": self.class_id,
            "class_name": self.class_name,
            "centroid": list(self.centroid),
            "has_mask": self.has_mask,
        }
        if self.angle_deg is not None:
            out["angle_deg"] = float(self.angle_deg)
        if self.area_px is not None:
            out["area_px"] = float(self.area_px)
        return out


@dataclass
class DetectionResult:
    """Resultado de uma inferência (todas as detecções de 1 frame)."""

    detections: List[Detection] = field(default_factory=list)
    inference_time_ms: float = 0.0
    frame_id: int = 0
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def best_detection(self) -> Optional[Detection]:
        """Detecção de maior confiança (comportamento histórico do sistema)."""
        if not self.detections:
            return None
        return max(self.detections, key=lambda d: d.confidence)

    def best_by_priority(
        self,
        confidence_weight: float = 1.0,
        area_weight: float = 1.0,
    ) -> Optional[Detection]:
        """
        Melhor detecção combinando confiança e área (normalizada).

        Permite ao robô priorizar embalagens grandes e bem detectadas,
        otimizando o deslocamento (menos viagens, pega mais robusta).
        Fórmula: score = confidence_weight * conf + area_weight * (area / max_area).

        Retorna None se não houver detecções.
        """
        if not self.detections:
            return None
        max_area = max(d.effective_area_px for d in self.detections) or 1.0
        def _score(d: Detection) -> float:
            return (
                confidence_weight * float(d.confidence)
                + area_weight * (d.effective_area_px / max_area)
            )
        return max(self.detections, key=_score)

    @property
    def count(self) -> int:
        return len(self.detections)

    @property
    def has_detections(self) -> bool:
        return len(self.detections) > 0

    def filter_by_confidence(self, threshold: float) -> List[Detection]:
        return [d for d in self.detections if d.confidence >= threshold]

    def filter_by_class(self, class_names: List[str]) -> List[Detection]:
        return [d for d in self.detections if d.class_name in class_names]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "detections": [d.to_dict() for d in self.detections],
            "inference_time_ms": self.inference_time_ms,
            "frame_id": self.frame_id,
            "timestamp": self.timestamp.isoformat(),
            "count": self.count,
        }


@dataclass
class DetectionEvent:
    """
    Evento de detecção para comunicação com CLP.

    Carrega os dados que a plataforma de pick precisa: X, Y (centroide),
    ângulo da embalagem, área e metadados auxiliares.
    """

    detected: bool
    class_name: str = ""
    confidence: float = 0.0
    bbox: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])
    centroid: Tuple[float, float] = (0.0, 0.0)
    angle_deg: Optional[float] = None
    area_px: Optional[float] = None
    source_id: str = ""
    frame_id: int = 0
    timestamp: datetime = field(default_factory=datetime.now)
    inference_time_ms: float = 0.0
    detection_count: int = 0

    @classmethod
    def from_result(
        cls,
        result: DetectionResult,
        source_id: str = "main",
        prioritize_area: bool = True,
    ) -> "DetectionEvent":
        """
        Cria evento a partir de DetectionResult.

        prioritize_area=True: usa `best_by_priority` (confiança + área).
        Útil para priorizar embalagens grandes no pick-and-place.
        """
        if prioritize_area:
            best = result.best_by_priority()
        else:
            best = result.best_detection

        if best is None:
            return cls(
                detected=False,
                source_id=source_id,
                frame_id=result.frame_id,
                timestamp=result.timestamp,
                inference_time_ms=result.inference_time_ms,
            )

        return cls(
            detected=True,
            class_name=best.class_name,
            confidence=best.confidence,
            bbox=best.bbox.to_list(),
            centroid=best.centroid,
            angle_deg=best.angle_deg,
            area_px=best.area_px,
            source_id=source_id,
            frame_id=result.frame_id,
            timestamp=result.timestamp,
            inference_time_ms=result.inference_time_ms,
            detection_count=result.count,
        )

    def to_plc_data(self) -> Dict[str, Any]:
        """
        Converte para dados do CLP.

        Inclui angle_deg (0 quando ausente) e area_px (0 quando ausente)
        para manter o contrato CLP estável mesmo sob modelos sem segmentação.
        """
        return {
            "product_detected": self.detected,
            "centroid_x": self.centroid[0],
            "centroid_y": self.centroid[1],
            "confidence": self.confidence,
            "angle_deg": float(self.angle_deg) if self.angle_deg is not None else 0.0,
            "area_px": float(self.area_px) if self.area_px is not None else 0.0,
            "detection_count": self.detection_count,
            "processing_time": self.inference_time_ms,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "detected": self.detected,
            "class_name": self.class_name,
            "confidence": self.confidence,
            "bbox": self.bbox,
            "centroid": {
                "x": self.centroid[0],
                "y": self.centroid[1],
            },
            "angle_deg": self.angle_deg,
            "area_px": self.area_px,
            "source_id": self.source_id,
            "frame_id": self.frame_id,
            "timestamp": self.timestamp.isoformat(),
            "inference_time_ms": self.inference_time_ms,
            "detection_count": self.detection_count,
        }
