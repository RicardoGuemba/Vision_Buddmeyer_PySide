# -*- coding: utf-8 -*-
"""
Gerenciamento de Region of Interest (ROI).
"""

from dataclasses import dataclass
from typing import Tuple, Optional, List, Union
import numpy as np

from PySide6.QtCore import QObject, Signal


def clamp_centroid_to_roi(
    cx: float,
    cy: float,
    roi: Union[Tuple[int, int, int, int], "ROI"],
) -> Tuple[float, float]:
    """
    Projeta o centroide (cx, cy) ao ponto mais próximo dentro do ROI.
    Usa projeção ortogonal (minimiza distância euclidiana).

    Args:
        cx: Coordenada X do centroide (px)
        cy: Coordenada Y do centroide (px)
        roi: ROI como (x, y, width, height) ou instância de ROI

    Returns:
        (cx_clamped, cy_clamped) - ponto dentro do ROI
    """
    if isinstance(roi, tuple):
        r = ROI.from_tuple(roi)
    else:
        r = roi
    return r.clamp_point(cx, cy)


@dataclass
class ROI:
    """Região de interesse."""
    
    x: int
    y: int
    width: int
    height: int
    
    @property
    def x2(self) -> int:
        """Coordenada X do canto inferior direito."""
        return self.x + self.width
    
    @property
    def y2(self) -> int:
        """Coordenada Y do canto inferior direito."""
        return self.y + self.height
    
    @property
    def center(self) -> Tuple[int, int]:
        """Centro do ROI."""
        return (self.x + self.width // 2, self.y + self.height // 2)
    
    @property
    def area(self) -> int:
        """Área do ROI."""
        return self.width * self.height
    
    def to_tuple(self) -> Tuple[int, int, int, int]:
        """Converte para tupla (x, y, width, height)."""
        return (self.x, self.y, self.width, self.height)
    
    def to_list(self) -> List[int]:
        """Converte para lista [x, y, width, height]."""
        return [self.x, self.y, self.width, self.height]
    
    def to_xyxy(self) -> Tuple[int, int, int, int]:
        """Converte para formato (x1, y1, x2, y2)."""
        return (self.x, self.y, self.x2, self.y2)
    
    @classmethod
    def from_tuple(cls, roi: Tuple[int, int, int, int]) -> "ROI":
        """Cria a partir de tupla (x, y, width, height)."""
        return cls(x=roi[0], y=roi[1], width=roi[2], height=roi[3])
    
    @classmethod
    def from_xyxy(cls, x1: int, y1: int, x2: int, y2: int) -> "ROI":
        """Cria a partir de coordenadas (x1, y1, x2, y2)."""
        return cls(x=x1, y=y1, width=x2 - x1, height=y2 - y1)
    
    def contains_point(self, x: int, y: int) -> bool:
        """Verifica se um ponto está dentro do ROI."""
        return self.x <= x < self.x2 and self.y <= y < self.y2
    
    def clamp_point(self, cx: float, cy: float) -> Tuple[float, float]:
        """
        Projeta o ponto (cx, cy) ao ponto mais próximo dentro do ROI.
        Usado para limitar coordenadas ao ROI evitando colisões com plataforma.

        Args:
            cx: Coordenada X do centroide (px)
            cy: Coordenada Y do centroide (px)

        Returns:
            (cx_clamped, cy_clamped) - ponto mais próximo dentro do ROI
        """
        x1, y1, x2, y2 = self.x, self.y, self.x2, self.y2
        cx_clamped = max(float(x1), min(float(x2), cx))
        cy_clamped = max(float(y1), min(float(y2), cy))
        return (cx_clamped, cy_clamped)

    def clip_to_frame(self, frame_width: int, frame_height: int) -> "ROI":
        """Ajusta ROI para caber no frame."""
        x = max(0, min(self.x, frame_width - 1))
        y = max(0, min(self.y, frame_height - 1))
        width = min(self.width, frame_width - x)
        height = min(self.height, frame_height - y)
        return ROI(x=x, y=y, width=width, height=height)
    
    def scale(self, scale_x: float, scale_y: float) -> "ROI":
        """Escala o ROI."""
        return ROI(
            x=int(self.x * scale_x),
            y=int(self.y * scale_y),
            width=int(self.width * scale_x),
            height=int(self.height * scale_y),
        )


class ROIManager(QObject):
    """
    Gerenciador de ROI.
    
    Signals:
        roi_changed: Emitido quando o ROI muda
    """
    
    roi_changed = Signal(object)  # ROI ou None
    
    def __init__(self):
        super().__init__()
        
        self._roi: Optional[ROI] = None
        self._frame_width: int = 0
        self._frame_height: int = 0
    
    def set_roi(self, roi: Optional[ROI]) -> None:
        """
        Define o ROI atual.
        
        Args:
            roi: Novo ROI ou None para desativar
        """
        self._roi = roi
        self.roi_changed.emit(roi)
    
    def set_roi_from_tuple(self, roi: Optional[Tuple[int, int, int, int]]) -> None:
        """Define ROI a partir de tupla."""
        if roi is None:
            self.set_roi(None)
        else:
            self.set_roi(ROI.from_tuple(roi))
    
    def set_frame_size(self, width: int, height: int) -> None:
        """Define tamanho do frame."""
        self._frame_width = width
        self._frame_height = height
    
    def clear_roi(self) -> None:
        """Remove o ROI."""
        self.set_roi(None)
    
    def get_roi(self) -> Optional[ROI]:
        """Retorna o ROI atual."""
        return self._roi
    
    def has_roi(self) -> bool:
        """Verifica se há ROI definido."""
        return self._roi is not None
    
    def apply_roi(self, frame: np.ndarray) -> np.ndarray:
        """
        Aplica o ROI ao frame.
        
        Args:
            frame: Frame de entrada
        
        Returns:
            Frame recortado ou original se não houver ROI
        """
        if self._roi is None:
            return frame
        
        h, w = frame.shape[:2]
        roi = self._roi.clip_to_frame(w, h)
        
        return frame[roi.y:roi.y2, roi.x:roi.x2].copy()
    
    def transform_coordinates(
        self,
        x: float,
        y: float,
        from_roi: bool = True,
    ) -> Tuple[float, float]:
        """
        Transforma coordenadas entre ROI e frame completo.
        
        Args:
            x: Coordenada X
            y: Coordenada Y
            from_roi: Se True, converte de ROI para frame; se False, de frame para ROI
        
        Returns:
            Coordenadas transformadas
        """
        if self._roi is None:
            return (x, y)
        
        if from_roi:
            # De ROI para frame
            return (x + self._roi.x, y + self._roi.y)
        else:
            # De frame para ROI
            return (x - self._roi.x, y - self._roi.y)
    
    def transform_bbox(
        self,
        bbox: Tuple[float, float, float, float],
        from_roi: bool = True,
    ) -> Tuple[float, float, float, float]:
        """
        Transforma bounding box entre ROI e frame completo.
        
        Args:
            bbox: (x1, y1, x2, y2)
            from_roi: Se True, converte de ROI para frame; se False, de frame para ROI
        
        Returns:
            Bounding box transformado
        """
        if self._roi is None:
            return bbox
        
        x1, y1, x2, y2 = bbox
        
        if from_roi:
            return (
                x1 + self._roi.x,
                y1 + self._roi.y,
                x2 + self._roi.x,
                y2 + self._roi.y,
            )
        else:
            return (
                x1 - self._roi.x,
                y1 - self._roi.y,
                x2 - self._roi.x,
                y2 - self._roi.y,
            )
