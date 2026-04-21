# -*- coding: utf-8 -*-
"""
Painel de status lateral.
"""

from typing import Optional, List, Tuple

from PySide6.QtCore import Qt, Slot, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QGroupBox, QGridLayout, QCheckBox, QSpinBox, QFormLayout
)
from PySide6.QtGui import QFont, QColor

from detection.events import DetectionEvent
from communication.connection_state import ConnectionState, ConnectionStatus
from config.settings import get_settings
from control.robot_controller import RobotControlState


class StatusIndicator(QFrame):
    """Indicador de status com LED."""
    
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)
        
        # LED
        self._led = QLabel()
        self._led.setFixedSize(12, 12)
        self._led.setStyleSheet("""
            QLabel {
                background-color: #c5c9ce;
                border-radius: 6px;
                border: 1px solid #1b3a69;
            }
        """)
        layout.addWidget(self._led)
        
        # Label
        self._label = QLabel(label)
        self._label.setStyleSheet("color: #e5e7eb;")
        layout.addWidget(self._label)
        
        layout.addStretch()
        
        # Status
        self._status_label = QLabel("---")
        self._status_label.setStyleSheet("color: #c5c9ce; font-size: 11px;")
        layout.addWidget(self._status_label)
    
    def set_status(self, status: str, color: str = "gray") -> None:
        """Define o status."""
        self._status_label.setText(status)
        
        colors = {
            "green": "#28a745",
            "yellow": "#ffc107",
            "red": "#dc3545",
            "blue": "#26477e",
            "gray": "#c5c9ce",
        }
        
        led_color = colors.get(color, colors["gray"])
        self._led.setStyleSheet(f"""
            QLabel {{
                background-color: {led_color};
                border-radius: 6px;
                border: 1px solid {led_color};
            }}
        """)


class StatusPanel(QWidget):
    """
    Painel de status lateral.
    
    Exibe:
    - Status do sistema
    - Status do CLP
    - Última detecção
    - ROI (Região de Interesse)
    """
    
    roi_changed = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setFixedWidth(280)
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Configura a interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)
        
        # Título
        title = QLabel("STATUS DO SISTEMA")
        title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        title.setStyleSheet("color: #26477e;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Separador
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("background-color: #1b3a69;")
        layout.addWidget(separator)
        
        # Status do Sistema
        system_group = QGroupBox("Sistema")
        system_group.setStyleSheet("""
            QGroupBox {
                color: #e5e7eb;
                border: 1px solid #1b3a69;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
            }
        """)
        system_layout = QVBoxLayout(system_group)
        
        self._system_status = StatusIndicator("Estado")
        system_layout.addWidget(self._system_status)
        
        self._stream_status = StatusIndicator("Stream")
        system_layout.addWidget(self._stream_status)
        
        self._inference_status = StatusIndicator("Detecção")
        system_layout.addWidget(self._inference_status)
        
        layout.addWidget(system_group)
        
        # Status do CLP
        plc_group = QGroupBox("CLP")
        plc_group.setStyleSheet(system_group.styleSheet())
        plc_layout = QVBoxLayout(plc_group)
        
        self._plc_status = StatusIndicator("Conexão")
        plc_layout.addWidget(self._plc_status)
        
        self._robot_status = StatusIndicator("Robô")
        plc_layout.addWidget(self._robot_status)
        
        self._robot_state = StatusIndicator("Estado")
        plc_layout.addWidget(self._robot_state)
        
        plc_layout.addWidget(QLabel("Último erro:"))
        self._last_error = QLabel("—")
        self._last_error.setStyleSheet("color: #dc3545; font-size: 11px;")
        self._last_error.setWordWrap(True)
        self._last_error.setMaximumHeight(36)
        plc_layout.addWidget(self._last_error)
        
        plc_layout.addWidget(QLabel("Latência CIP:"))
        self._latency_ms = QLabel("— ms")
        self._latency_ms.setStyleSheet("color: #26477e; font-size: 11px;")
        plc_layout.addWidget(self._latency_ms)
        
        layout.addWidget(plc_group)
        
        # Última Detecção
        detection_group = QGroupBox("Última Detecção")
        detection_group.setStyleSheet(system_group.styleSheet())
        detection_layout = QGridLayout(detection_group)
        
        detection_layout.addWidget(QLabel("Classe:"), 0, 0)
        self._det_class = QLabel("---")
        self._det_class.setStyleSheet("color: #26477e; font-weight: bold; font-size: 11px;")
        detection_layout.addWidget(self._det_class, 0, 1)
        
        detection_layout.addWidget(QLabel("Confiança:"), 1, 0)
        self._det_confidence = QLabel("---")
        self._det_confidence.setStyleSheet("color: #28a745; font-size: 11px;")
        detection_layout.addWidget(self._det_confidence, 1, 1)
        
        detection_layout.addWidget(QLabel("Centroide X:"), 2, 0)
        self._det_x = QLabel("---")
        self._det_x.setStyleSheet("color: #e5e7eb; font-size: 11px;")
        detection_layout.addWidget(self._det_x, 2, 1)
        
        detection_layout.addWidget(QLabel("Centroide Y:"), 3, 0)
        self._det_y = QLabel("---")
        self._det_y.setStyleSheet("color: #e5e7eb; font-size: 11px;")
        detection_layout.addWidget(self._det_y, 3, 1)

        detection_layout.addWidget(QLabel("Ângulo (°):"), 4, 0)
        self._det_angle = QLabel("---")
        self._det_angle.setStyleSheet("color: #ffcc00; font-weight: bold; font-size: 11px;")
        detection_layout.addWidget(self._det_angle, 4, 1)

        detection_layout.addWidget(QLabel("Área:"), 5, 0)
        self._det_area = QLabel("---")
        self._det_area.setStyleSheet("color: #e5e7eb; font-size: 11px;")
        detection_layout.addWidget(self._det_area, 5, 1)

        layout.addWidget(detection_group)
        
        # ROI: apenas ligar/desligar (configuração em Configuração → Imagem)
        roi_group = QGroupBox("ROI")
        roi_group.setStyleSheet(system_group.styleSheet())
        roi_group.setToolTip("Liga ou desliga a região de interesse. Configure coordenadas em Configuração → Imagem.")
        roi_layout = QFormLayout(roi_group)
        self._roi_enabled = QCheckBox("Ativar ROI")
        roi_layout.addRow("", self._roi_enabled)
        self._roi_x = QSpinBox()
        self._roi_x.setRange(0, 9999)
        self._roi_y = QSpinBox()
        self._roi_y.setRange(0, 9999)
        self._roi_w = QSpinBox()
        self._roi_w.setRange(1, 9999)
        self._roi_h = QSpinBox()
        self._roi_h.setRange(1, 9999)
        roi_hidden = QWidget()
        roi_hidden.setVisible(False)
        hl = QHBoxLayout(roi_hidden)
        hl.addWidget(self._roi_x)
        hl.addWidget(self._roi_y)
        hl.addWidget(self._roi_w)
        hl.addWidget(self._roi_h)
        roi_layout.addRow("", roi_hidden)
        self._roi_enabled.stateChanged.connect(lambda: self.roi_changed.emit())
        layout.addWidget(roi_group)
        
        layout.addStretch()
    
    @Slot(str)
    def set_system_status(self, status: str) -> None:
        """Define status do sistema."""
        color_map = {
            "RUNNING": "green",
            "PAUSED": "yellow",
            "STOPPED": "gray",
            "ERROR": "red",
        }
        self._system_status.set_status(status, color_map.get(status, "gray"))
    
    @Slot(bool)
    def set_stream_running(self, running: bool) -> None:
        """Define status do stream."""
        if running:
            self._stream_status.set_status("Ativo", "green")
        else:
            self._stream_status.set_status("Parado", "gray")
    
    @Slot(bool)
    def set_inference_running(self, running: bool) -> None:
        """Define status da inferência."""
        if running:
            self._inference_status.set_status("Ativo", "green")
        else:
            self._inference_status.set_status("Parado", "gray")
    
    @Slot(object)
    def set_connection_state(self, state: ConnectionState) -> None:
        """Define estado da conexão CLP."""
        status_map = {
            ConnectionStatus.CONNECTED: ("Conectado", "green"),
            ConnectionStatus.SIMULATED: ("Simulado", "blue"),
            ConnectionStatus.CONNECTING: ("Conectando...", "yellow"),
            ConnectionStatus.DISCONNECTED: ("Desconectado", "gray"),
            ConnectionStatus.DEGRADED: ("Degradado", "yellow"),
            ConnectionStatus.ERROR: ("Erro", "red"),
        }
        status, color = status_map.get(state.status, ("Desconhecido", "gray"))
        self._plc_status.set_status(status, color)
    
    @Slot(str)
    def set_robot_state(self, state: str) -> None:
        """Define estado do robô."""
        color_map = {
            "INITIALIZING": "yellow",
            "WAITING_AUTHORIZATION": "yellow",
            "DETECTING": "green",
            "WAITING_SEND_AUTHORIZATION": "yellow",  # Modo manual: aguarda operador autorizar envio ao CLP
            "SENDING_DATA": "green",
            "WAITING_ACK": "yellow",
            "ACK_CONFIRMED": "green",
            "WAITING_PICK": "yellow",
            "WAITING_PLACE": "yellow",
            "WAITING_CYCLE_START": "yellow",
            "READY_FOR_NEXT": "green",
            "ERROR": "red",
            "TIMEOUT": "red",
            "SAFETY_BLOCKED": "red",
            "STOPPED": "gray",
        }
        self._robot_state.set_status(state, color_map.get(state, "gray"))
    
    @Slot(object)
    def update_detection(self, event: DetectionEvent) -> None:
        """Atualiza informações da detecção (centroide em px ou mm conforme calibração)."""
        if event.detected:
            self._det_class.setText(event.class_name)
            self._det_confidence.setText(f"{event.confidence:.1%}")
            cx_px, cy_px = event.centroid[0], event.centroid[1]
            mm_per_px = getattr(
                get_settings().preprocess, "roi_calibration_mm_per_px", 1.0
            ) or 1.0
            cx, cy = cx_px * mm_per_px, cy_px * mm_per_px
            self._det_x.setText(f"{cx:.1f}")
            self._det_y.setText(f"{cy:.1f}")

            angle = getattr(event, "angle_deg", None)
            if angle is not None:
                self._det_angle.setText(f"{float(angle):.1f}")
            else:
                self._det_angle.setText("—")

            area_px = getattr(event, "area_px", None)
            if area_px is not None:
                area_scaled = float(area_px) * (mm_per_px ** 2)
                unit = "mm²" if abs(mm_per_px - 1.0) > 1e-6 else "px²"
                self._det_area.setText(f"{area_scaled:.0f} {unit}")
            else:
                self._det_area.setText("—")
        else:
            self._det_class.setText("---")
            self._det_confidence.setText("---")
            self._det_x.setText("---")
            self._det_y.setText("---")
            self._det_angle.setText("---")
            self._det_area.setText("---")
    
    def set_roi(self, enabled: bool, x: int = 0, y: int = 0, w: int = 640, h: int = 480) -> None:
        """Define ROI (bloqueia sinais para evitar loop)."""
        self._roi_enabled.blockSignals(True)
        self._roi_x.blockSignals(True)
        self._roi_y.blockSignals(True)
        self._roi_w.blockSignals(True)
        self._roi_h.blockSignals(True)
        self._roi_enabled.setChecked(enabled)
        self._roi_x.setValue(x)
        self._roi_y.setValue(y)
        self._roi_w.setValue(w)
        self._roi_h.setValue(h)
        self._roi_enabled.blockSignals(False)
        self._roi_x.blockSignals(False)
        self._roi_y.blockSignals(False)
        self._roi_w.blockSignals(False)
        self._roi_h.blockSignals(False)
    
    def get_roi(self) -> Tuple[bool, List[int]]:
        """Retorna (enabled, [x, y, w, h])."""
        if self._roi_enabled.isChecked():
            return True, [
                self._roi_x.value(),
                self._roi_y.value(),
                self._roi_w.value(),
                self._roi_h.value(),
            ]
        return False, [0, 0, 640, 480]
    
    def set_last_error(self, error: str) -> None:
        """Define último erro exibido (RF-06: UI informativa)."""
        if not error:
            self._last_error.setText("—")
        else:
            self._last_error.setText(error[:80] + ("…" if len(error) > 80 else ""))
    
    def set_latency_ms(self, ms: Optional[float]) -> None:
        """Define latência CIP em ms (RF-06: latência aproximada)."""
        if ms is None:
            self._latency_ms.setText("— ms")
        else:
            self._latency_ms.setText(f"{ms:.0f} ms")
