# -*- coding: utf-8 -*-
"""
Widget de vídeo com overlay de detecções.
"""

from typing import Optional, List
import numpy as np

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy
from PySide6.QtCore import Qt, Signal, Slot, QTimer, QRect, QSize
from PySide6.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QFont

from detection.events import Detection, DetectionResult


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
        
        Exibe apenas o centroide da detecção de maior confiança,
        destacando-o com um marcador maior e mais visível.
        """
        if not self._current_detections:
            return
        
        # Encontra a detecção de maior confiança
        best_detection = max(self._current_detections, key=lambda d: d.confidence)
        color = self._get_color_for_confidence(best_detection.confidence)
        
        # Bounding box da melhor detecção
        bbox = best_detection.bbox
        x1 = int(bbox.x1 * scale_x) + offset_x
        y1 = int(bbox.y1 * scale_y) + offset_y
        x2 = int(bbox.x2 * scale_x) + offset_x
        y2 = int(bbox.y2 * scale_y) + offset_y
        
        # Desenha retângulo apenas para a melhor detecção
        pen = QPen(color, 3)  # Mais grosso para destacar
        painter.setPen(pen)
        painter.drawRect(x1, y1, x2 - x1, y2 - y1)
        
        # Desenha centroide da melhor detecção (maior e mais destacado)
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        
        # Círculo maior preenchido
        from PySide6.QtGui import QBrush
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(Qt.white, 2))
        painter.drawEllipse(cx - 10, cy - 10, 20, 20)
        
        # Cruz no centro do centroide
        painter.setPen(QPen(Qt.black, 2))
        painter.drawLine(cx - 8, cy, cx + 8, cy)
        painter.drawLine(cx, cy - 8, cx, cy + 8)
        
        # Coordenadas do centroide (em pixels da imagem original)
        centroid_x_original = (bbox.x1 + bbox.x2) / 2
        centroid_y_original = (bbox.y1 + bbox.y2) / 2
        
        # Desenha label com coordenadas
        label = f"{best_detection.class_name} {best_detection.confidence:.0%}"
        coord_label = f"({centroid_x_original:.0f}, {centroid_y_original:.0f})"
        
        font = QFont("Segoe UI", 10, QFont.Bold)
        painter.setFont(font)
        
        # Background do label principal
        label_rect = QRect(x1, y1 - 22, len(label) * 9, 20)
        painter.fillRect(label_rect, color)
        
        # Texto do label principal
        painter.setPen(QPen(Qt.black))
        painter.drawText(label_rect, Qt.AlignCenter, label)
        
        # Background do label de coordenadas (abaixo do bbox)
        coord_rect = QRect(cx - 50, y2 + 5, 100, 18)
        painter.fillRect(coord_rect, QColor(0, 0, 0, 180))
        
        # Texto das coordenadas
        painter.setPen(QPen(Qt.white))
        painter.drawText(coord_rect, Qt.AlignCenter, coord_label)
    
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
