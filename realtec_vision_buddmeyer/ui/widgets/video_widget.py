# -*- coding: utf-8 -*-
"""
Widget de vídeo com overlay de detecções.
"""

from typing import Optional, List

import numpy as np

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy
from PySide6.QtCore import Qt, Signal, Slot, QTimer, QRect, QSize, QPointF
from PySide6.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QFont, QBrush, QPolygonF

import math

from config import get_settings
from detection.events import Detection, DetectionResult
from preprocessing.roi_manager import clamp_centroid_to_roi


class VideoWidget(QWidget):
    """
    Widget para exibição de vídeo com overlay de detecções.
    
    Signals:
        clicked: Emitido quando o widget é clicado
        double_clicked: Emitido quando o widget recebe duplo clique
    """
    
    clicked = Signal()
    double_clicked = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self._current_frame: Optional[np.ndarray] = None
        self._current_detections: List[Detection] = []
        self._show_overlay = True
        self._show_fps = True
        self._current_fps = 0.0
        # Cache para evitar conversão numpy→QImage→QPixmap a cada paintEvent (reduz travamentos)
        self._cached_pixmap: Optional[QPixmap] = None
        self._cached_paint_size: Optional[QSize] = None
        self._cached_frame_shape: Optional[tuple] = None
        self._cached_offset_scale: Optional[tuple] = None  # (x, y, scale_x, scale_y)
        
        # Cores para detecções por confiança
        self._colors = {
            "high": QColor(0, 255, 0),      # Verde - confiança > 0.8
            "medium": QColor(255, 255, 0),  # Amarelo - confiança > 0.5
            "low": QColor(255, 165, 0),     # Laranja - confiança > 0.3
            "very_low": QColor(255, 0, 0),  # Vermelho - confiança < 0.3
        }
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Configura a interface."""
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background-color: #14284c;")
        
        # Label para quando não há vídeo
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self._placeholder_label = QLabel("Aguardando vídeo...")
        self._placeholder_label.setAlignment(Qt.AlignCenter)
        self._placeholder_label.setStyleSheet("""
            QLabel {
                color: #c5c9ce;
                font-size: 16px;
                font-weight: bold;
            }
        """)
        layout.addWidget(self._placeholder_label)
    
    @Slot(np.ndarray)
    def update_frame(self, frame: np.ndarray) -> None:
        """
        Atualiza o frame exibido.
        
        Args:
            frame: Frame BGR do OpenCV
        """
        self._current_frame = frame
        self._placeholder_label.hide()
        # Invalida cache para repintar na próxima paintEvent
        self._cached_frame_shape = None
        self.update()
    
    @Slot(object)
    def update_detections(self, result: DetectionResult) -> None:
        """
        Atualiza as detecções exibidas.
        
        Args:
            result: Resultado da detecção
        """
        self._current_detections = result.detections
        self.update()
    
    def set_fps(self, fps: float) -> None:
        """Define o FPS atual."""
        self._current_fps = fps
        if self._show_fps:
            self.update()
    
    def set_show_overlay(self, show: bool) -> None:
        """Define se mostra overlay de detecções."""
        self._show_overlay = show
        self.update()
    
    def set_show_fps(self, show: bool) -> None:
        """Define se mostra FPS."""
        self._show_fps = show
        self.update()
    
    def clear(self) -> None:
        """Limpa o widget."""
        self._current_frame = None
        self._current_detections = []
        self._cached_pixmap = None
        self._cached_paint_size = None
        self._cached_frame_shape = None
        self._cached_offset_scale = None
        self._placeholder_label.show()
        self.update()
    
    def _ensure_cached_pixmap(self) -> bool:
        """Converte o frame atual em QPixmap em cache (só recalcula se frame ou tamanho mudou). Retorna True se há frame para desenhar."""
        if self._current_frame is None:
            return False
        frame = self._current_frame
        h, w = frame.shape[:2]
        ch = frame.shape[2] if len(frame.shape) > 2 else 1
        if ch == 1:
            return False
        widget_size = self.size()
        frame_shape = (w, h)
        if (
            self._cached_pixmap is not None
            and self._cached_frame_shape == frame_shape
            and self._cached_paint_size == widget_size
        ):
            return True
        bytes_per_line = ch * w
        rgb_frame = frame[:, :, ::-1].copy()
        q_image = QImage(
            rgb_frame.data,
            w, h,
            bytes_per_line,
            QImage.Format_RGB888
        )
        scaled_pixmap = QPixmap.fromImage(q_image).scaled(
            widget_size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        x = (widget_size.width() - scaled_pixmap.width()) // 2
        y = (widget_size.height() - scaled_pixmap.height()) // 2
        scale_x = scaled_pixmap.width() / w
        scale_y = scaled_pixmap.height() / h
        self._cached_pixmap = scaled_pixmap
        self._cached_paint_size = QSize(widget_size)
        self._cached_frame_shape = frame_shape
        self._cached_offset_scale = (x, y, scale_x, scale_y)
        return True
    
    def resizeEvent(self, event) -> None:
        """Invalida cache ao redimensionar para redesenhar na nova escala."""
        self._cached_paint_size = None
        super().resizeEvent(event)
    
    def paintEvent(self, event) -> None:
        """Evento de pintura (usa cache para evitar conversão pesada a cada repaint)."""
        super().paintEvent(event)
        
        if not self._ensure_cached_pixmap():
            return
        
        x, y, scale_x, scale_y = self._cached_offset_scale
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.drawPixmap(x, y, self._cached_pixmap)
        if self._show_overlay and self._current_detections:
            self._draw_detections(painter, x, y, scale_x, scale_y)
        if self._show_fps:
            self._draw_fps(painter)
        painter.end()
    
    def _draw_detections(
        self,
        painter: QPainter,
        offset_x: int,
        offset_y: int,
        scale_x: float,
        scale_y: float,
    ) -> None:
        """
        Desenha as detecções no frame.

        Para segmentação (Mask2Former):
          - contorno da máscara na cor de confiança
          - centroide geométrico (preciso)
          - vetor do eixo maior (ângulo da embalagem)
          - label com ângulo e área

        Para object detection clássico (fallback):
          - bbox + centroide do bbox
        """
        if not self._current_detections:
            return

        # Prefere a detecção com maior score combinado (confiança + área) quando disponível
        best_detection = self._select_best(self._current_detections)
        color = self._get_color_for_confidence(best_detection.confidence)

        # Bounding box
        bbox = best_detection.bbox
        x1 = int(bbox.x1 * scale_x) + offset_x
        y1 = int(bbox.y1 * scale_y) + offset_y
        x2 = int(bbox.x2 * scale_x) + offset_x
        y2 = int(bbox.y2 * scale_y) + offset_y

        # Overlay da máscara (contorno) quando existir
        if best_detection.has_mask and best_detection.mask is not None:
            self._draw_mask_contour(
                painter, best_detection.mask, color, offset_x, offset_y, scale_x, scale_y,
            )
        else:
            pen = QPen(color, 3)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(x1, y1, x2 - x1, y2 - y1)

        # Centroide (prioriza o do mask quando existir)
        cx_f, cy_f = best_detection.centroid
        cx = int(cx_f * scale_x) + offset_x
        cy = int(cy_f * scale_y) + offset_y

        painter.setBrush(QBrush(color))
        painter.setPen(QPen(Qt.white, 2))
        painter.drawEllipse(cx - 10, cy - 10, 20, 20)
        painter.setPen(QPen(Qt.black, 2))
        painter.drawLine(cx - 8, cy, cx + 8, cy)
        painter.drawLine(cx, cy - 8, cx, cy + 8)

        # Eixo maior (vetor que indica orientação da embalagem)
        if best_detection.has_orientation:
            self._draw_major_axis(
                painter, best_detection, color, offset_x, offset_y, scale_x, scale_y,
            )

        # Centroide limitado ao ROI (amarelo)
        roi = get_settings().preprocess.roi
        if roi is not None and len(roi) == 4:
            clamped_x, clamped_y = clamp_centroid_to_roi(
                cx_f, cy_f, tuple(roi)
            )
            cx_clamped = int(clamped_x * scale_x) + offset_x
            cy_clamped = int(clamped_y * scale_y) + offset_y
            yellow = QColor(255, 255, 0)
            painter.setBrush(QBrush(yellow))
            painter.setPen(QPen(Qt.black, 2))
            size = 12
            diamond = QPolygonF([
                QPointF(cx_clamped, cy_clamped - size),
                QPointF(cx_clamped + size, cy_clamped),
                QPointF(cx_clamped, cy_clamped + size),
                QPointF(cx_clamped - size, cy_clamped),
            ])
            painter.drawPolygon(diamond)

        # Labels
        label = f"{best_detection.class_name} {best_detection.confidence:.0%}"
        coord_label = f"({cx_f:.0f}, {cy_f:.0f})"
        extra_parts: List[str] = []
        if best_detection.angle_deg is not None:
            extra_parts.append(f"{best_detection.angle_deg:.1f}°")
        if best_detection.area_px is not None:
            extra_parts.append(f"A={best_detection.area_px:.0f}px²")
        extra_label = " | ".join(extra_parts)

        font = QFont("Segoe UI", 10, QFont.Bold)
        painter.setFont(font)

        label_rect = QRect(x1, y1 - 22, max(len(label) * 9, 60), 20)
        painter.fillRect(label_rect, color)
        painter.setPen(QPen(Qt.black))
        painter.drawText(label_rect, Qt.AlignCenter, label)

        coord_rect = QRect(cx - 50, y2 + 5, 100, 18)
        painter.fillRect(coord_rect, QColor(0, 0, 0, 180))
        painter.setPen(QPen(Qt.white))
        painter.drawText(coord_rect, Qt.AlignCenter, coord_label)

        if extra_label:
            extra_rect = QRect(cx - 90, y2 + 25, 180, 18)
            painter.fillRect(extra_rect, QColor(0, 0, 0, 180))
            painter.setPen(QPen(QColor(255, 255, 0)))
            painter.drawText(extra_rect, Qt.AlignCenter, extra_label)

    @staticmethod
    def _select_best(detections: List[Detection]) -> Detection:
        """Seleciona a melhor detecção combinando confiança e área (normalizada)."""
        if len(detections) == 1:
            return detections[0]
        try:
            max_area = max(d.effective_area_px for d in detections) or 1.0
        except Exception:
            return max(detections, key=lambda d: d.confidence)
        return max(
            detections,
            key=lambda d: d.confidence + (d.effective_area_px / max_area) * 0.5,
        )

    def _draw_mask_contour(
        self,
        painter: QPainter,
        mask: np.ndarray,
        color: QColor,
        offset_x: int,
        offset_y: int,
        scale_x: float,
        scale_y: float,
    ) -> None:
        """Desenha o contorno da máscara e um overlay translúcido."""
        try:
            import cv2
        except ImportError:
            return
        if mask is None:
            return
        bin_mask = mask.astype(np.uint8)
        contours, _ = cv2.findContours(
            bin_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE,
        )
        if not contours:
            return
        pen = QPen(color, 2)
        painter.setPen(pen)
        fill = QColor(color)
        fill.setAlpha(64)
        painter.setBrush(QBrush(fill))
        for contour in contours:
            if contour.shape[0] < 3:
                continue
            poly = QPolygonF()
            for pt in contour.reshape(-1, 2):
                px = float(pt[0]) * scale_x + offset_x
                py = float(pt[1]) * scale_y + offset_y
                poly.append(QPointF(px, py))
            painter.drawPolygon(poly)

    def _draw_major_axis(
        self,
        painter: QPainter,
        detection: Detection,
        color: QColor,
        offset_x: int,
        offset_y: int,
        scale_x: float,
        scale_y: float,
    ) -> None:
        """Desenha o vetor do eixo maior (ângulo da embalagem) passando pelo centroide."""
        angle = float(detection.angle_deg or 0.0)
        cx_f, cy_f = detection.centroid
        # Comprimento do eixo: proxy a partir do bbox para estabilidade visual.
        length = 0.5 * max(detection.bbox.width, detection.bbox.height)
        dx = math.cos(math.radians(angle)) * length
        dy = math.sin(math.radians(angle)) * length

        p1x = int((cx_f - dx) * scale_x) + offset_x
        p1y = int((cy_f - dy) * scale_y) + offset_y
        p2x = int((cx_f + dx) * scale_x) + offset_x
        p2y = int((cy_f + dy) * scale_y) + offset_y

        pen = QPen(QColor(255, 0, 255), 3)  # magenta, alto contraste
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(p1x, p1y, p2x, p2y)

        # Ponta da seta no lado "positivo" do eixo
        head = 10
        painter.drawEllipse(p2x - 5, p2y - 5, 10, 10)
    
    def _draw_fps(self, painter: QPainter) -> None:
        """Desenha o FPS no canto."""
        font = QFont("Segoe UI", 12, QFont.Bold)
        painter.setFont(font)
        
        fps_text = f"FPS: {self._current_fps:.1f}"
        
        # Background
        rect = QRect(10, 10, 90, 25)
        painter.fillRect(rect, QColor(0, 0, 0, 180))
        
        # Cor baseada no FPS
        if self._current_fps >= 25:
            color = QColor(0, 255, 0)
        elif self._current_fps >= 15:
            color = QColor(255, 255, 0)
        else:
            color = QColor(255, 0, 0)
        
        painter.setPen(QPen(color))
        painter.drawText(rect, Qt.AlignCenter, fps_text)
    
    def _get_color_for_confidence(self, confidence: float) -> QColor:
        """Retorna cor baseada na confiança."""
        if confidence >= 0.8:
            return self._colors["high"]
        elif confidence >= 0.5:
            return self._colors["medium"]
        elif confidence >= 0.3:
            return self._colors["low"]
        else:
            return self._colors["very_low"]
    
    def mousePressEvent(self, event) -> None:
        """Evento de clique."""
        self.clicked.emit()
        super().mousePressEvent(event)
    
    def mouseDoubleClickEvent(self, event) -> None:
        """Evento de duplo clique."""
        self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)
