# -*- coding: utf-8 -*-
"""Painel de status lateral — Mark2 + visão."""

from typing import Optional, List, Tuple

from PySide6.QtCore import Qt, Slot, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QGroupBox, QCheckBox, QSpinBox, QFormLayout
)

from detection.events import DetectionEvent
from config.settings import get_settings


class StatusIndicator(QFrame):
    """Indicador de status com LED."""

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)
        self._led = QLabel()
        self._led.setFixedSize(12, 12)
        self._led.setStyleSheet(
            "QLabel { background-color: #c5c9ce; border-radius: 6px; border: 1px solid #1b3a69; }"
        )
        layout.addWidget(self._led)
        self._label = QLabel(label)
        self._label.setStyleSheet("color: #e5e7eb;")
        layout.addWidget(self._label)
        layout.addStretch()
        self._status_label = QLabel("---")
        self._status_label.setStyleSheet("color: #c5c9ce; font-size: 11px;")
        layout.addWidget(self._status_label)

    def set_status(self, status: str, color: str = "gray") -> None:
        self._status_label.setText(status)
        colors = {
            "green": "#28a745",
            "yellow": "#ffc107",
            "red": "#dc3545",
            "blue": "#26477e",
            "gray": "#c5c9ce",
        }
        led_color = colors.get(color, colors["gray"])
        self._led.setStyleSheet(
            f"QLabel {{ background-color: {led_color}; border-radius: 6px; border: 1px solid {led_color}; }}"
        )


class StatusPanel(QWidget):
    """Painel lateral: sistema, Mark2, última detecção, ROI."""

    roi_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(300)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        system_group = QGroupBox("Sistema")
        system_group.setStyleSheet(self._group_style())
        system_layout = QVBoxLayout(system_group)
        self._stream_status = StatusIndicator("Stream")
        system_layout.addWidget(self._stream_status)
        self._model_status = StatusIndicator("Modelo")
        system_layout.addWidget(self._model_status)
        self._fps_label = QLabel("FPS: —")
        self._fps_label.setStyleSheet("color: #c5c9ce;")
        system_layout.addWidget(self._fps_label)
        layout.addWidget(system_group)

        mark2_group = QGroupBox("Mark2")
        mark2_group.setStyleSheet(self._group_style())
        mark2_layout = QFormLayout(mark2_group)
        self._mark2_conn = StatusIndicator("Conexão")
        mark2_layout.addRow(self._mark2_conn)
        self._robot_state = QLabel("DISCONNECTED")
        self._robot_state.setStyleSheet("color: #e5e7eb; font-weight: bold;")
        mark2_layout.addRow("Estado:", self._robot_state)
        self._serial_port = QLabel(get_settings().mark2.serial.port)
        self._serial_port.setStyleSheet("color: #c5c9ce; font-size: 11px;")
        mark2_layout.addRow("Porta:", self._serial_port)
        self._last_cmd = QLabel("—")
        self._last_cmd.setStyleSheet("color: #c5c9ce; font-size: 11px;")
        mark2_layout.addRow("Último cmd:", self._last_cmd)
        self._angles_label = QLabel("B:— O:— C:— G:—")
        self._angles_label.setStyleSheet("color: #c5c9ce; font-size: 11px;")
        mark2_layout.addRow("Ângulos:", self._angles_label)
        self._pick_label = QLabel("—")
        self._pick_label.setStyleSheet("color: #c5c9ce; font-size: 11px;")
        mark2_layout.addRow("Pega px:", self._pick_label)
        self._xyz_label = QLabel("—")
        self._xyz_label.setStyleSheet("color: #c5c9ce; font-size: 11px;")
        mark2_layout.addRow("XYZ mm:", self._xyz_label)
        self._reachable_label = QLabel("—")
        self._reachable_label.setStyleSheet("color: #c5c9ce;")
        mark2_layout.addRow("Alcançável:", self._reachable_label)
        self._last_error = QLabel("—")
        self._last_error.setStyleSheet("color: #dc3545; font-size: 11px;")
        self._last_error.setWordWrap(True)
        mark2_layout.addRow("Erro:", self._last_error)
        layout.addWidget(mark2_group)

        det_group = QGroupBox("Última detecção")
        det_group.setStyleSheet(self._group_style())
        det_layout = QFormLayout(det_group)
        self._det_class = QLabel("—")
        self._det_conf = QLabel("—")
        self._det_xy = QLabel("—")
        for w in (self._det_class, self._det_conf, self._det_xy):
            w.setStyleSheet("color: #c5c9ce;")
        det_layout.addRow("Classe:", self._det_class)
        det_layout.addRow("Confiança:", self._det_conf)
        det_layout.addRow("Centroide:", self._det_xy)
        layout.addWidget(det_group)

        roi_group = QGroupBox("ROI")
        roi_group.setStyleSheet(self._group_style())
        roi_layout = QVBoxLayout(roi_group)
        self._roi_enabled = QCheckBox("Ativar ROI")
        self._roi_enabled.stateChanged.connect(lambda *_: self.roi_changed.emit())
        roi_layout.addWidget(self._roi_enabled)
        form = QFormLayout()
        self._roi_x = QSpinBox(); self._roi_x.setRange(0, 10000)
        self._roi_y = QSpinBox(); self._roi_y.setRange(0, 10000)
        self._roi_w = QSpinBox(); self._roi_w.setRange(1, 10000)
        self._roi_h = QSpinBox(); self._roi_h.setRange(1, 10000)
        for sp in (self._roi_x, self._roi_y, self._roi_w, self._roi_h):
            sp.valueChanged.connect(lambda *_: self.roi_changed.emit())
        form.addRow("X:", self._roi_x)
        form.addRow("Y:", self._roi_y)
        form.addRow("W:", self._roi_w)
        form.addRow("H:", self._roi_h)
        roi_layout.addLayout(form)
        layout.addWidget(roi_group)
        layout.addStretch()

        # Defaults ROI
        s = get_settings()
        if s.preprocess.roi and len(s.preprocess.roi) == 4:
            self._roi_enabled.setChecked(True)
            self._roi_x.setValue(int(s.preprocess.roi[0]))
            self._roi_y.setValue(int(s.preprocess.roi[1]))
            self._roi_w.setValue(int(s.preprocess.roi[2]))
            self._roi_h.setValue(int(s.preprocess.roi[3]))

    @staticmethod
    def _group_style() -> str:
        return """
            QGroupBox {
                color: #e5e7eb;
                border: 1px solid #1b3a69;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 8px;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; }
        """

    def get_roi(self) -> Tuple[bool, Optional[List[int]]]:
        if not self._roi_enabled.isChecked():
            return False, None
        return True, [
            self._roi_x.value(),
            self._roi_y.value(),
            self._roi_w.value(),
            self._roi_h.value(),
        ]

    def set_roi(self, enabled: bool, x: int = 0, y: int = 0, w: int = 1, h: int = 1) -> None:
        self._roi_enabled.setChecked(bool(enabled))
        self._roi_x.setValue(int(x))
        self._roi_y.setValue(int(y))
        self._roi_w.setValue(max(1, int(w)))
        self._roi_h.setValue(max(1, int(h)))

    @Slot(str)
    def set_stream_status(self, status: str, color: str = "gray") -> None:
        self._stream_status.set_status(status, color)

    def set_stream_running(self, running: bool) -> None:
        if running:
            self._stream_status.set_status("Activo", "green")
        else:
            self._stream_status.set_status("Parado", "gray")

    def set_inference_running(self, running: bool) -> None:
        if running:
            self._model_status.set_status("Activo", "green")
        else:
            self._model_status.set_status("Parado", "gray")

    def set_system_status(self, status: str) -> None:
        color = "green" if status.upper() in ("RUNNING", "OK") else (
            "yellow" if status.upper() == "PAUSED" else "gray"
        )
        self._stream_status.set_status(status, color)

    @Slot(str)
    def set_model_status(self, status: str, color: str = "gray") -> None:
        self._model_status.set_status(status, color)

    @Slot(float)
    def set_fps(self, fps: float) -> None:
        self._fps_label.setText(f"FPS: {fps:.1f}")

    @Slot(bool)
    def set_mark2_connected(self, connected: bool) -> None:
        if connected:
            self._mark2_conn.set_status("Conectado", "green")
        else:
            self._mark2_conn.set_status("Desconectado", "red")

    # Compatibilidade
    def set_mark2_link_status(self, status: str, color: str = "gray") -> None:
        self._mark2_conn.set_status(status, color)

    def set_robot_status(self, status: str, color: str = "gray") -> None:
        self._mark2_conn.set_status(status, color)

    @Slot(str)
    def set_robot_state(self, state: str) -> None:
        self._robot_state.setText(state)

    def set_serial_port(self, port: str) -> None:
        self._serial_port.setText(port)

    def set_last_command(self, cmd: str) -> None:
        self._last_cmd.setText(cmd)

    def set_angles(self, angles: dict) -> None:
        self._angles_label.setText(
            f"B:{angles.get('base','—')} O:{angles.get('shoulder','—')} "
            f"C:{angles.get('elbow','—')} G:{angles.get('gripper','—')}"
        )

    def set_pick_and_coords(self, coords: dict) -> None:
        px = coords.get("pixel")
        robot = coords.get("robot_mm")
        reachable = coords.get("reachable")
        if px:
            self._pick_label.setText(f"({px[0]:.0f}, {px[1]:.0f})")
        if robot:
            z = get_settings().mark2.heights.package_z_mm
            self._xyz_label.setText(f"({robot[0]:.1f}, {robot[1]:.1f}, {z:.1f})")
        if reachable is None:
            self._reachable_label.setText("—")
        else:
            self._reachable_label.setText("sim" if reachable else "não")
            self._reachable_label.setStyleSheet(
                "color: #28a745;" if reachable else "color: #dc3545;"
            )

    def set_last_error(self, error: str) -> None:
        self._last_error.setText(error or "—")

    @Slot(object)
    def update_detection(self, event: DetectionEvent) -> None:
        if not event or not event.detected:
            self._det_class.setText("—")
            self._det_conf.setText("—")
            self._det_xy.setText("—")
            return
        self._det_class.setText(event.class_name or "—")
        self._det_conf.setText(f"{event.confidence:.0%}")
        mm = get_settings().preprocess.roi_calibration_mm_per_px or 1.0
        cx, cy = event.centroid
        self._det_xy.setText(f"({cx * mm:.0f}, {cy * mm:.0f}) mm")
