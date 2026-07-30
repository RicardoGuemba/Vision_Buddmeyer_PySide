# -*- coding: utf-8 -*-
"""Wizard de calibração Mark2: homografia, origem e validação."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QDoubleSpinBox, QFormLayout,
    QGroupBox, QMessageBox, QSplitter, QHeaderView, QSpinBox,
)

from config import get_settings
from config.settings import Mark2Settings
from core.logger import get_logger
from robot.mark2_calibration import Mark2Calibration
from streaming import StreamManager
from ui.widgets.video_widget import VideoWidget

logger = get_logger("ui.mark2_calibration")


class Mark2CalibrationPage(QWidget):
    """Calibração de coordenadas visão ↔ Mark2 (sem Arduino obrigatório)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._settings = get_settings()
        self._stream = StreamManager()
        self._calib = Mark2Calibration(
            self._settings.mark2.calibration,
            self._settings.mark2.reference,
            self._settings.mark2.workspace,
        )
        self._image_points: List[List[float]] = list(
            self._settings.mark2.calibration.image_points or []
        )
        self._world_points: List[List[float]] = list(
            self._settings.mark2.calibration.world_points_mm or []
        )
        self._pending_uv: Optional[Tuple[float, float]] = None
        self._setup_ui()
        self._refresh_table()
        self._update_live_from_pending()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel("Calibração Mark2 — sincronização de coordenadas")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #e5e7eb;")
        layout.addWidget(title)

        splitter = QSplitter(Qt.Horizontal)

        left = QWidget()
        left_l = QVBoxLayout(left)
        self._video = VideoWidget()
        self._video.frame_clicked.connect(self._on_frame_clicked)
        left_l.addWidget(self._video)
        hint = QLabel("Clique no vídeo para capturar (u, v). Depois introduza Xw, Yw em mm.")
        hint.setStyleSheet("color: #c5c9ce;")
        left_l.addWidget(hint)
        splitter.addWidget(left)

        right = QWidget()
        right_l = QVBoxLayout(right)

        # Passo 1
        g1 = QGroupBox("1. Pontos imagem ↔ mundo (≥4)")
        g1l = QVBoxLayout(g1)
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["u px", "v px", "Xw mm", "Yw mm"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        g1l.addWidget(self._table)
        row = QHBoxLayout()
        self._xw = QDoubleSpinBox(); self._xw.setRange(-2000, 2000); self._xw.setSuffix(" mm")
        self._yw = QDoubleSpinBox(); self._yw.setRange(-2000, 2000); self._yw.setSuffix(" mm")
        row.addWidget(QLabel("Xw:")); row.addWidget(self._xw)
        row.addWidget(QLabel("Yw:")); row.addWidget(self._yw)
        add_btn = QPushButton("Adicionar ponto pendente")
        add_btn.clicked.connect(self._add_pending_point)
        row.addWidget(add_btn)
        rem_btn = QPushButton("Remover seleccionado")
        rem_btn.clicked.connect(self._remove_selected)
        row.addWidget(rem_btn)
        g1l.addLayout(row)
        compute_btn = QPushButton("Calcular homografia")
        compute_btn.clicked.connect(self._compute_homography)
        g1l.addWidget(compute_btn)
        right_l.addWidget(g1)

        # Passo 2
        g2 = QGroupBox("2. Origem e rotação da base Mark2")
        g2f = QFormLayout(g2)
        self._ox = QDoubleSpinBox(); self._ox.setRange(-2000, 2000)
        self._oy = QDoubleSpinBox(); self._oy.setRange(-2000, 2000)
        self._rot = QDoubleSpinBox(); self._rot.setRange(-180, 180)
        self._ox.setValue(self._settings.mark2.reference.origin_x_mm)
        self._oy.setValue(self._settings.mark2.reference.origin_y_mm)
        self._rot.setValue(self._settings.mark2.reference.rotation_deg)
        g2f.addRow("Origin X mm:", self._ox)
        g2f.addRow("Origin Y mm:", self._oy)
        g2f.addRow("Rotation deg:", self._rot)
        apply_ref = QPushButton("Aplicar origem/rotação")
        apply_ref.clicked.connect(self._apply_reference)
        g2f.addRow(apply_ref)
        right_l.addWidget(g2)

        # Passo 3
        g3 = QGroupBox("3. Validação RMSE")
        g3l = QVBoxLayout(g3)
        self._rmse_label = QLabel("RMSE: —")
        self._rmse_label.setStyleSheet("color: #e5e7eb; font-weight: bold;")
        g3l.addWidget(self._rmse_label)
        val_btn = QPushButton("Validar pontos da tabela")
        val_btn.clicked.connect(self._validate)
        g3l.addWidget(val_btn)
        right_l.addWidget(g3)

        # Live
        g4 = QGroupBox("Projecção live")
        g4f = QFormLayout(g4)
        self._live_px = QLabel("—")
        self._live_world = QLabel("—")
        self._live_robot = QLabel("—")
        self._live_reach = QLabel("—")
        for w in (self._live_px, self._live_world, self._live_robot, self._live_reach):
            w.setStyleSheet("color: #c5c9ce;")
        g4f.addRow("px:", self._live_px)
        g4f.addRow("world mm:", self._live_world)
        g4f.addRow("robot mm:", self._live_robot)
        g4f.addRow("alcançável:", self._live_reach)
        right_l.addWidget(g4)

        save_btn = QPushButton("Guardar calibração (mark2.yaml)")
        save_btn.setStyleSheet("background-color: #26477e; color: white; font-weight: bold; padding: 8px;")
        save_btn.clicked.connect(self._save)
        right_l.addWidget(save_btn)
        right_l.addStretch()

        splitter.addWidget(right)
        splitter.setSizes([700, 400])
        layout.addWidget(splitter)

    def bind_stream_frames(self) -> None:
        """Liga frames do StreamManager (se a operação já estiver a correr)."""
        try:
            self._stream.frame_info_available.disconnect(self._on_frame)
        except Exception:
            pass
        self._stream.frame_info_available.connect(self._on_frame)

    @Slot(object)
    def _on_frame(self, frame_info) -> None:
        frame = frame_info.frame if hasattr(frame_info, "frame") else frame_info
        if frame is not None:
            self._video.update_frame(frame)

    @Slot(float, float)
    def _on_frame_clicked(self, u: float, v: float) -> None:
        self._pending_uv = (u, v)
        self._video.set_pick_point((u, v))
        self._update_live_from_pending()
        logger.info("calibration_click", u=u, v=v)

    def _add_pending_point(self) -> None:
        if self._pending_uv is None:
            QMessageBox.information(self, "Calibração", "Clique primeiro no vídeo.")
            return
        u, v = self._pending_uv
        self._image_points.append([float(u), float(v)])
        self._world_points.append([float(self._xw.value()), float(self._yw.value())])
        self._pending_uv = None
        self._refresh_table()

    def _remove_selected(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._image_points):
            return
        self._image_points.pop(row)
        self._world_points.pop(row)
        self._refresh_table()

    def _refresh_table(self) -> None:
        self._table.setRowCount(len(self._image_points))
        for i, ((u, v), (x, y)) in enumerate(zip(self._image_points, self._world_points)):
            self._table.setItem(i, 0, QTableWidgetItem(f"{u:.1f}"))
            self._table.setItem(i, 1, QTableWidgetItem(f"{v:.1f}"))
            self._table.setItem(i, 2, QTableWidgetItem(f"{x:.1f}"))
            self._table.setItem(i, 3, QTableWidgetItem(f"{y:.1f}"))

    def _compute_homography(self) -> None:
        try:
            self._calib.compute_homography(self._image_points, self._world_points)
            QMessageBox.information(self, "Calibração", "Homografia calculada.")
            self._update_live_from_pending()
        except Exception as exc:
            QMessageBox.warning(self, "Calibração", str(exc))

    def _apply_reference(self) -> None:
        self._calib.set_reference(self._ox.value(), self._oy.value(), self._rot.value())
        self._settings.mark2.reference.origin_x_mm = self._ox.value()
        self._settings.mark2.reference.origin_y_mm = self._oy.value()
        self._settings.mark2.reference.rotation_deg = self._rot.value()
        self._update_live_from_pending()

    def _validate(self) -> None:
        try:
            rmse = self._calib.validate_points(self._image_points, self._world_points)
            ok = rmse <= self._settings.mark2.calibration.max_rmse_mm
            self._rmse_label.setText(
                f"RMSE: {rmse:.3f} mm — {'OK' if ok else 'ACIMA DO LIMITE'}"
            )
            self._rmse_label.setStyleSheet(
                "color: #28a745; font-weight: bold;" if ok else "color: #dc3545; font-weight: bold;"
            )
        except Exception as exc:
            QMessageBox.warning(self, "Validação", str(exc))

    def _update_live_from_pending(self) -> None:
        uv = self._pending_uv
        if uv is None and self._image_points:
            uv = tuple(self._image_points[-1])
        if uv is None:
            return
        triple = self._calib.project(uv[0], uv[1], self._settings.mark2.heights.package_z_mm)
        self._live_px.setText(f"({triple.pixel[0]:.1f}, {triple.pixel[1]:.1f})")
        if triple.world_mm:
            self._live_world.setText(f"({triple.world_mm[0]:.2f}, {triple.world_mm[1]:.2f})")
        else:
            self._live_world.setText(triple.message or "—")
        if triple.robot_mm:
            self._live_robot.setText(f"({triple.robot_mm[0]:.2f}, {triple.robot_mm[1]:.2f})")
        else:
            self._live_robot.setText("—")
        self._live_reach.setText("sim" if triple.reachable else f"não ({triple.message})")

    def _save(self) -> None:
        self._apply_reference()
        self._settings.mark2.calibration = self._calib.to_settings()
        self._settings.mark2.calibration.image_points = self._image_points
        self._settings.mark2.calibration.world_points_mm = self._world_points
        path = Path(__file__).resolve().parents[2] / "config" / "mark2.yaml"
        self._settings.mark2.save_yaml(path)
        # reload settings cache
        get_settings(reload=True)
        QMessageBox.information(self, "Calibração", f"Guardado em {path}")
