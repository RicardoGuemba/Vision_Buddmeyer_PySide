# -*- coding: utf-8 -*-
"""
Página de Operação - Aba principal para operação do sistema.
"""

import time
from pathlib import Path
from typing import List, Optional

import numpy as np

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QPushButton, QComboBox, QLabel, QFileDialog,
    QSplitter, QGroupBox, QCheckBox, QMessageBox,
)
from PySide6.QtCore import Qt, Slot, QTimer, Signal
from PySide6.QtGui import QFont, QKeySequence, QShortcut

from config import get_settings
from core.logger import get_logger
from streaming import StreamManager
from streaming.mjpeg_server import MjpegServer
from detection import InferenceEngine
from robot import Mark2Controller

from ui.widgets.video_widget import VideoWidget
from ui.widgets.status_panel import StatusPanel
from ui.widgets.event_console import EventConsole
from ui.widgets.gentl_camera_settings_dialog import GenTLCameraSettingsDialog


class OperationPage(QWidget):
    """
    Página de Operação.
    
    Contém:
    - Widget de vídeo com detecções
    - Painel de status lateral
    - Console de eventos
    - Controles de operação
    """
    
    model_preload_finished = Signal(bool)  # True = modelo carregado em segundo plano
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self._logger = get_logger("ui.operation")
        self._settings = get_settings()
        self._stream_manager = StreamManager()
        self._inference_engine = InferenceEngine()
        self._mark2 = Mark2Controller()
        
        self._is_running = False
        self._mjpeg_server: Optional[MjpegServer] = None
        
        self._detection_count = 0  # Contador total de detecções
        self._error_count = 0  # Contador total de erros
        
        # Carregamento do modelo na GUI thread (PyTorch/MPS não é estável em QThread)
        self._model_loading = False
        self._shutdown_requested = False
        self._pending_start_source_label: Optional[str] = None
        
        self._setup_ui()
        self._apply_mvp_ui_visibility()
        self._sync_combo_to_settings()
        self._connect_signals()
        self._setup_shortcuts()
    
    def _apply_mvp_ui_visibility(self) -> None:
        """Mostra controlos Mark2 (sempre visíveis na operação)."""
        for widget in (
            self._mark2_connect_btn,
            self._mark2_disconnect_btn,
            self._mode_combo,
            self._authorize_send_btn,
            self._mark2_home_btn,
            self._mark2_open_gripper_btn,
            self._mark2_close_gripper_btn,
            self._mark2_test_move_btn,
            self._mark2_execute_pnp_btn,
            self._mark2_stop_btn,
            self._mark2_reset_btn,
            self._smoke_cb,
        ):
            widget.setVisible(True)
        self._status_step_label.setText("Mark2: desconectado")
    
    def _setup_ui(self) -> None:
        """Configura a interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # Splitter principal (horizontal)
        main_splitter = QSplitter(Qt.Horizontal)
        
        # Área central (vídeo + console)
        central_widget = QWidget()
        central_layout = QVBoxLayout(central_widget)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(8)
        
        # Widget de vídeo
        self._video_widget = VideoWidget()
        self._video_widget.double_clicked.connect(self._toggle_fullscreen)
        central_layout.addWidget(self._video_widget, stretch=3)
        
        # Legenda da fonte atual (abaixo do vídeo)
        self._source_caption = QLabel()
        self._source_caption.setStyleSheet("color: #c5c9ce; font-size: 11px; padding: 2px 0;")
        self._source_caption.setAlignment(Qt.AlignCenter)
        central_layout.addWidget(self._source_caption)
        
        # Console de eventos
        console_group = QGroupBox("Eventos")
        console_group.setStyleSheet("""
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
        console_layout = QVBoxLayout(console_group)
        self._event_console = EventConsole()
        self._event_console.setMinimumHeight(140)
        console_layout.addWidget(self._event_console)
        central_layout.addWidget(console_group, stretch=1)
        
        main_splitter.addWidget(central_widget)
        
        # Painel de status (direita)
        self._status_panel = StatusPanel()
        main_splitter.addWidget(self._status_panel)
        
        # Proporções do splitter
        main_splitter.setSizes([800, 280])
        
        layout.addWidget(main_splitter, stretch=1)
        
        # Barra de status da etapa atual (pick-and-place)
        status_bar = QFrame()
        status_bar.setStyleSheet("""
            QFrame {
                background-color: #14284c;
                border: 1px solid #1b3a69;
                border-radius: 4px;
            }
        """)
        status_bar.setMinimumHeight(44)
        status_bar_layout = QHBoxLayout(status_bar)
        status_bar_layout.setContentsMargins(12, 8, 12, 8)
        status_label = QLabel("Status atual:")
        status_label.setStyleSheet("color: #c5c9ce; font-size: 11px; font-weight: bold;")
        status_bar_layout.addWidget(status_label)
        self._status_step_label = QLabel("—")
        self._status_step_label.setStyleSheet("color: #26477e; font-weight: bold; font-size: 11px;")
        self._status_step_label.setWordWrap(True)
        status_bar_layout.addWidget(self._status_step_label, stretch=1)
        layout.addWidget(status_bar)

        # Controles inferiores — duas faixas para evitar truncagem
        controls_wrap = QVBoxLayout()
        controls_wrap.setSpacing(6)

        # --- Linha 1: fonte + ciclo de visão ---
        vision_frame = QFrame()
        vision_frame.setStyleSheet("""
            QFrame {
                background-color: #14284c;
                border: 1px solid #1b3a69;
                border-radius: 4px;
            }
            QLabel { color: #c5c9ce; }
        """)
        vision_row = QHBoxLayout(vision_frame)
        vision_row.setContentsMargins(12, 8, 12, 8)
        vision_row.setSpacing(8)

        vision_row.addWidget(QLabel("Fonte:"))
        self._source_combo = QComboBox()
        self._source_combo.setMinimumWidth(160)
        self._source_combo.setMaximumWidth(220)
        self._source_combo.addItems([
            "Arquivo de Vídeo",
            "Câmera USB",
            "Câmera GigE",
            "Câmera GenTL",
        ])
        self._source_combo.currentIndexChanged.connect(self._on_source_changed)
        vision_row.addWidget(self._source_combo)

        self._source_path_btn = QPushButton("Selecionar…")
        self._source_path_btn.setMinimumWidth(100)
        self._source_path_btn.clicked.connect(self._select_video_file)
        vision_row.addWidget(self._source_path_btn)

        self._gentl_cti_btn = QPushButton("Selecionar CTI…")
        self._gentl_cti_btn.setToolTip("Selecionar arquivo CTI GenTL")
        self._gentl_cti_btn.clicked.connect(self._select_gentl_cti_file)
        self._gentl_cti_btn.setVisible(False)
        self._gentl_cti_btn.setMinimumWidth(120)
        vision_row.addWidget(self._gentl_cti_btn)

        self._gentl_settings_btn = QPushButton("Ajustes câmera…")
        self._gentl_settings_btn.setToolTip("Ajustes GenTL (gain, exposição). Requer stream activo.")
        self._gentl_settings_btn.clicked.connect(self._open_gentl_camera_settings)
        self._gentl_settings_btn.setVisible(False)
        self._gentl_settings_btn.setMinimumWidth(120)
        vision_row.addWidget(self._gentl_settings_btn)

        vision_row.addStretch(1)

        btn_run = """
            QPushButton {
                color: white; font-weight: bold; padding: 8px 14px;
                border-radius: 4px; min-width: 96px;
            }
            QPushButton:disabled { background-color: #6c757d; }
        """
        self._play_btn = QPushButton("▶ Iniciar")
        self._play_btn.setStyleSheet(btn_run + "QPushButton { background-color: #28a745; } QPushButton:hover { background-color: #218838; }")
        self._play_btn.clicked.connect(self._start_system)
        vision_row.addWidget(self._play_btn)

        self._pause_btn = QPushButton("⏸ Pausar")
        self._pause_btn.setEnabled(False)
        self._pause_btn.setStyleSheet(
            btn_run
            + "QPushButton { background-color: #ffc107; color: black; }"
            + "QPushButton:hover { background-color: #e0a800; }"
            + "QPushButton:disabled { color: white; background-color: #6c757d; }"
        )
        self._pause_btn.clicked.connect(self._toggle_pause)
        vision_row.addWidget(self._pause_btn)

        self._stop_btn = QPushButton("⏹ Parar")
        self._stop_btn.setEnabled(False)
        self._stop_btn.setStyleSheet(btn_run + "QPushButton { background-color: #dc3545; } QPushButton:hover { background-color: #c82333; }")
        self._stop_btn.clicked.connect(self._stop_system)
        vision_row.addWidget(self._stop_btn)

        self._exit_btn = QPushButton("Sair")
        self._exit_btn.setToolTip("Encerra o sistema (Cmd+Q no macOS)")
        self._exit_btn.setMinimumWidth(72)
        self._exit_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d; color: white;
                padding: 8px 14px; border-radius: 4px;
            }
            QPushButton:hover { background-color: #5a6268; }
        """)
        self._exit_btn.clicked.connect(self._on_exit_clicked)
        vision_row.addWidget(self._exit_btn)

        controls_wrap.addWidget(vision_frame)

        # --- Linha 2: Mark2 ---
        mark2_frame = QFrame()
        mark2_frame.setStyleSheet("""
            QFrame {
                background-color: #14284c;
                border: 1px solid #1b3a69;
                border-radius: 4px;
            }
            QLabel { color: #c5c9ce; }
            QCheckBox { color: #e5e7eb; }
        """)
        mark2_col = QVBoxLayout(mark2_frame)
        mark2_col.setContentsMargins(12, 8, 12, 8)
        mark2_col.setSpacing(6)

        mark2_style = """
            QPushButton {
                background-color: #26477e;
                color: white;
                font-weight: bold;
                padding: 7px 12px;
                border-radius: 4px;
                min-width: 110px;
            }
            QPushButton:hover { background-color: #1b3a69; }
            QPushButton:disabled { background-color: #6c757d; }
        """
        mark2_danger = """
            QPushButton {
                background-color: #a71d2a;
                color: white;
                font-weight: bold;
                padding: 7px 12px;
                border-radius: 4px;
                min-width: 110px;
            }
            QPushButton:hover { background-color: #8b1822; }
            QPushButton:disabled { background-color: #6c757d; }
        """

        row_a = QHBoxLayout()
        row_a.setSpacing(8)
        title_m2 = QLabel("Mark2")
        title_m2.setStyleSheet("color: #e5e7eb; font-weight: bold;")
        row_a.addWidget(title_m2)

        self._mark2_connect_btn = QPushButton("Conectar")
        self._mark2_connect_btn.setStyleSheet(mark2_style)
        self._mark2_connect_btn.clicked.connect(self._mark2_connect)
        row_a.addWidget(self._mark2_connect_btn)

        self._mark2_disconnect_btn = QPushButton("Desconectar")
        self._mark2_disconnect_btn.setStyleSheet(mark2_style)
        self._mark2_disconnect_btn.clicked.connect(self._mark2_disconnect)
        row_a.addWidget(self._mark2_disconnect_btn)

        row_a.addWidget(QLabel("Modo:"))
        self._mode_combo = QComboBox()
        self._mode_combo.setMinimumWidth(100)
        self._mode_combo.addItem("Manual", "manual")
        self._mode_combo.addItem("Semi", "semi")
        self._mode_combo.addItem("Auto", "auto")
        mode = self._settings.mark2.operation.mode
        idx = max(0, self._mode_combo.findData(mode))
        self._mode_combo.setCurrentIndex(idx)
        self._mode_combo.currentIndexChanged.connect(self._on_mark2_mode_changed)
        row_a.addWidget(self._mode_combo)

        self._authorize_send_btn = QPushButton("Autorizar PnP")
        self._authorize_send_btn.setEnabled(False)
        self._authorize_send_btn.setStyleSheet(mark2_style)
        self._authorize_send_btn.setToolTip(
            "Modo semi: objecto estável — autoriza pick-and-place."
        )
        self._authorize_send_btn.clicked.connect(self._authorize_pick)
        row_a.addWidget(self._authorize_send_btn)

        self._smoke_cb = QCheckBox("Novo movimento embalagem → motor 1s")
        self._smoke_cb.setChecked(self._settings.mark2.operation.smoke_detection_trigger)
        self._smoke_cb.setToolTip(
            "Quando a embalagem se desloca (≥ tolerância px), aciona a garra uma vez "
            "durante ~1 segundo. Não repete sem novo movimento."
        )
        self._smoke_cb.stateChanged.connect(self._on_smoke_mode_changed)
        row_a.addWidget(self._smoke_cb)
        row_a.addStretch(1)
        mark2_col.addLayout(row_a)

        row_b = QHBoxLayout()
        row_b.setSpacing(8)

        self._mark2_home_btn = QPushButton("Home")
        self._mark2_home_btn.setStyleSheet(mark2_style)
        self._mark2_home_btn.clicked.connect(self._mark2.home)
        row_b.addWidget(self._mark2_home_btn)

        self._mark2_open_gripper_btn = QPushButton("Abrir garra")
        self._mark2_open_gripper_btn.setStyleSheet(mark2_style)
        self._mark2_open_gripper_btn.clicked.connect(self._mark2.open_gripper)
        row_b.addWidget(self._mark2_open_gripper_btn)

        self._mark2_close_gripper_btn = QPushButton("Fechar garra")
        self._mark2_close_gripper_btn.setStyleSheet(mark2_style)
        self._mark2_close_gripper_btn.clicked.connect(self._mark2.close_gripper)
        row_b.addWidget(self._mark2_close_gripper_btn)

        self._mark2_test_move_btn = QPushButton("Testar movimento")
        self._mark2_test_move_btn.setStyleSheet(mark2_style)
        self._mark2_test_move_btn.clicked.connect(self._mark2.test_move)
        row_b.addWidget(self._mark2_test_move_btn)

        self._mark2_execute_pnp_btn = QPushButton("Executar PnP")
        self._mark2_execute_pnp_btn.setStyleSheet(mark2_style)
        self._mark2_execute_pnp_btn.clicked.connect(self._mark2.execute_pick_place_locked)
        row_b.addWidget(self._mark2_execute_pnp_btn)

        self._mark2_stop_btn = QPushButton("STOP")
        self._mark2_stop_btn.setStyleSheet(mark2_danger)
        self._mark2_stop_btn.clicked.connect(self._mark2.stop)
        row_b.addWidget(self._mark2_stop_btn)

        self._mark2_reset_btn = QPushButton("Reset erro")
        self._mark2_reset_btn.setStyleSheet(mark2_style)
        self._mark2_reset_btn.clicked.connect(self._mark2.reset_error)
        row_b.addWidget(self._mark2_reset_btn)

        row_b.addStretch(1)
        mark2_col.addLayout(row_b)

        controls_wrap.addWidget(mark2_frame)
        layout.addLayout(controls_wrap)
    
    def _load_roi_from_settings(self) -> None:
        """Carrega ROI das configurações para o painel. Padrão: metade da área a partir do centro."""
        from config.settings import DEFAULT_ROI_QUARTER_AREA

        s = self._settings.preprocess
        if s.roi and len(s.roi) == 4:
            self._status_panel.set_roi(True, s.roi[0], s.roi[1], s.roi[2], s.roi[3])
        else:
            # ROI padrão: metade da área centralizada (ex.: 640x480 -> 320x240)
            x, y, w, h = DEFAULT_ROI_QUARTER_AREA
            self._status_panel.set_roi(True, x, y, w, h)
            s.roi = list(DEFAULT_ROI_QUARTER_AREA)  # aplica em memória para pipeline
        self._refresh_centroid_display()

    def _refresh_centroid_display(self) -> None:
        """Atualiza exibição do centroide no painel (usa calibração atual)."""
        from detection.events import DetectionEvent

        result = self._inference_engine.last_result
        if result is None:
            return
        event = DetectionEvent.from_result(
            result,
            plc_threshold=self._settings.detection.plc_confidence_threshold,
        )
        if event.detected:
            self._status_panel.update_detection(event)
    
    def _on_roi_changed(self) -> None:
        """Atualiza settings quando ROI muda (persistência via Salvar Config)."""
        enabled, coords = self._status_panel.get_roi()
        self._settings.preprocess.roi = coords if enabled else None
    
    def _sync_combo_to_settings(self) -> None:
        """Sincroniza o combo de fonte com o source_type do settings."""
        source_type_map = {"video": 0, "usb": 1, "gige": 2, "gentl": 3}
        current_source = self._settings.streaming.source_type
        combo_index = source_type_map.get(current_source, 1)  # 1 = usb como padrão
        self._source_combo.setCurrentIndex(combo_index)
        # Atualiza visibilidade dos botões de seleção (vídeo vs GenTL)
        self._source_path_btn.setVisible(combo_index == 0)
        self._gentl_cti_btn.setVisible(combo_index == 3)
        self._gentl_settings_btn.setVisible(combo_index == 3)
        self._update_source_caption()
    
    def _update_source_caption(self) -> None:
        """Atualiza a legenda da fonte atual (abaixo do vídeo)."""
        idx = self._source_combo.currentIndex()
        if idx == 0:
            path = self._settings.streaming.video_path or "—"
            name = Path(path).name if path != "—" else path
            self._source_caption.setText(f"Fonte: Arquivo de vídeo — {name}")
        elif idx == 1:
            cam = self._settings.streaming.usb_camera_index
            self._source_caption.setText(f"Fonte: Câmera USB (índice {cam})")
        elif idx == 2:
            self._source_caption.setText("Fonte: Câmera GigE")
        else:
            cti = (self._settings.streaming.gentl_cti_path or "").strip()
            if cti:
                self._source_caption.setText(f"Fonte: Câmera GenTL — {Path(cti).name}")
            else:
                self._source_caption.setText("Fonte: Câmera GenTL — use 'Selecionar CTI…'")
    
    def _connect_signals(self) -> None:
        """Conecta os sinais."""
        # Stream (ROI aplicado em _on_frame_available antes de exibir e inferir)
        self._stream_manager.frame_info_available.connect(self._on_frame_available)
        self._stream_manager.stream_started.connect(self._on_stream_started)
        self._stream_manager.stream_stopped.connect(self._on_stream_stopped)
        self._stream_manager.stream_error.connect(self._on_stream_error)
        
        # Inferência
        self._inference_engine.detection_result.connect(self._video_widget.update_detections)
        self._inference_engine.detection_result.connect(self._on_detection_result)
        self._inference_engine.detection_event.connect(self._on_detection)

        # Mark2
        self._mark2.state_changed.connect(self._status_panel.set_robot_state)
        self._mark2.state_changed.connect(self._on_mark2_state_changed)
        self._mark2.status_message.connect(self._status_step_label.setText)
        self._mark2.status_message.connect(self._video_widget.set_robot_status_text)
        self._mark2.connected_changed.connect(self._status_panel.set_mark2_connected)
        self._mark2.coordinates_updated.connect(self._on_mark2_coordinates)
        self._mark2.angles_changed.connect(self._status_panel.set_angles)
        self._mark2.error_occurred.connect(self._on_mark2_error)
        self._mark2.cycle_completed.connect(self._on_mark2_cycle_completed)
        self._mark2.package_locked.connect(self._on_mark2_package_locked)
        
        # ROI (persiste em settings; Salvar Config na aba Configuração persiste no arquivo)
        self._status_panel.roi_changed.connect(self._on_roi_changed)
        self._load_roi_from_settings()
        
        # Timer para atualizar FPS
        self._fps_timer = QTimer(self)
        self._fps_timer.timeout.connect(self._update_fps)
        self._fps_timer.start(500)
    
    def _setup_shortcuts(self) -> None:
        """Configura atalhos de teclado."""
        # F5 - Iniciar
        start_shortcut = QShortcut(QKeySequence("F5"), self)
        start_shortcut.activated.connect(self._start_system)
        
        # F6 - Parar
        stop_shortcut = QShortcut(QKeySequence("F6"), self)
        stop_shortcut.activated.connect(self._stop_system)
        
        # F11 - Fullscreen
        fullscreen_shortcut = QShortcut(QKeySequence("F11"), self)
        fullscreen_shortcut.activated.connect(self._toggle_fullscreen)
    
    @Slot()
    def _start_system(self) -> None:
        """Inicia o sistema."""
        if self._is_running:
            return
        
        # Determina fonte selecionada na UI
        source_types = ["video", "usb", "gige", "gentl"]
        source_labels = ["Arquivo de Vídeo", "Câmera USB", "Câmera GigE", "Câmera GenTL"]
        source_index = self._source_combo.currentIndex()
        source_type = source_types[source_index]
        
        self._event_console.add_info(
            f"Iniciando sistema com fonte: {source_labels[source_index]}..."
        )
        self._logger.info("start_system_requested", source_type=source_type)
        
        # Atualiza fonte em memória
        self._settings.streaming.source_type = source_type
        
        # Validação prévia para GenTL (arquivo CTI)
        if source_type == "gentl":
            cti_path_str = (self._settings.streaming.gentl_cti_path or "").strip()
            if not cti_path_str:
                self._event_console.add_error(
                    "Arquivo CTI GenTL não configurado. Use o botão 'Selecionar CTI...' para escolher "
                    "o arquivo .cti (ex.: Omron Sentech) ou configure na aba Configuração."
                )
                self._logger.error("gentl_cti_empty_on_start")
                return
            cti_path = Path(cti_path_str)
            if not cti_path.exists():
                self._event_console.add_error(
                    f"Arquivo CTI não encontrado:\n{cti_path}\n\n"
                    "Use 'Selecionar CTI...' para escolher o arquivo correto."
                )
                self._logger.error("gentl_cti_not_found_on_start", path=str(cti_path))
                return
        
        # Validação prévia específica para vídeo (arquivo)
        if source_type == "video":
            video_path_str = self._settings.streaming.video_path
            video_path = Path(video_path_str)
            
            # Normaliza caminho (resolve relativos e absolutos)
            if not video_path.is_absolute():
                base_path = Path(__file__).parent.parent.parent
                video_path = base_path / video_path_str
            
            try:
                video_path = video_path.resolve()
            except Exception as e:
                self._logger.warning("path_resolve_failed", path=str(video_path), error=str(e))
            
            # Verifica se arquivo existe
            if not video_path.exists():
                error_msg = (
                    f"Arquivo de vídeo não encontrado:\n"
                    f"{video_path}\n\n"
                    f"Por favor, selecione um arquivo válido usando o botão 'Selecionar...'"
                )
                self._event_console.add_error(error_msg)
                self._logger.error("video_not_found_on_start", path=str(video_path))
                return
            
            # Verifica se é um arquivo válido (não é diretório)
            if not video_path.is_file():
                error_msg = f"O caminho especificado não é um arquivo: {video_path}"
                self._event_console.add_error(error_msg)
                self._logger.error("video_path_is_not_file", path=str(video_path))
                return
            
            # Testa se OpenCV consegue abrir o arquivo
            import cv2
            test_cap = cv2.VideoCapture(str(video_path))
            if not test_cap.isOpened():
                test_cap.release()
                error_msg = (
                    f"Não foi possível abrir o arquivo de vídeo:\n"
                    f"{video_path}\n\n"
                    f"O arquivo pode estar corrompido ou em formato não suportado.\n"
                    f"Formatos suportados: MP4, AVI, MOV, MKV"
                )
                self._event_console.add_error(error_msg)
                self._logger.error("video_cannot_open", path=str(video_path))
                return
            test_cap.release()
            
            # Atualiza com caminho normalizado
            self._settings.streaming.video_path = str(video_path)
            self._logger.info("video_validated", path=str(video_path))
        
        # Atualiza configuração do StreamManager com os parâmetros da fonte
        # change_source() atualiza o singleton em memória; start() usará esses valores
        if source_type == "video":
            self._stream_manager.change_source(
                source_type=source_type,
                video_path=self._settings.streaming.video_path,
                loop_video=self._settings.streaming.loop_video,
            )
        elif source_type == "usb":
            self._stream_manager.change_source(
                source_type=source_type,
                camera_index=self._settings.streaming.usb_camera_index,
            )
        elif source_type == "gige":
            self._stream_manager.change_source(
                source_type=source_type,
                gige_ip=self._settings.streaming.gige_ip,
                gige_port=self._settings.streaming.gige_port,
            )
        elif source_type == "gentl":
            self._stream_manager.change_source(
                source_type=source_type,
                gentl_cti_path=self._settings.streaming.gentl_cti_path,
                gentl_device_index=self._settings.streaming.gentl_device_index,
            )
        
        # Inicia stream (usa configurações em memória, NÃO recarrega do YAML)
        if not self._stream_manager.start():
            self._event_console.add_error(
                f"Falha ao iniciar stream ({source_labels[source_index]})"
            )
            return
        
        self._event_console.add_info(
            f"Stream iniciado: {source_labels[source_index]}"
        )
        
        source_label = source_labels[source_index]
        
        # Carrega modelo na GUI thread (agendado; evita crash MPS/CUDA em QThread)
        if not self._inference_engine.is_model_loaded:
            if self._model_loading:
                self._pending_start_source_label = source_label
                self._play_btn.setText("Carregando modelo...")
                self._play_btn.setEnabled(False)
                return
            self._event_console.add_info(
                "Carregando modelo de detecção... (pode levar 1–2 min na primeira vez)"
            )
            self._play_btn.setText("Carregando modelo...")
            self._play_btn.setEnabled(False)
            self._schedule_model_load(pending_start_label=source_label)
            return
        
        self._finish_start_system_after_model(source_label)
    
    def _finish_start_system_after_model(self, source_label: str) -> None:
        """Conclui a inicialização após o modelo estar carregado (inferência, Mark2, UI)."""
        if not self._inference_engine.start():
            self._event_console.add_error("Falha ao iniciar inferência")
            self._stream_manager.stop()
            return
        self._event_console.add_info("Inferência iniciada - detecção ativa")
        self._connect_mark2()
        self._is_running = True

        if self._settings.output.rtsp_enabled:
            self._mjpeg_server = MjpegServer(
                host="0.0.0.0",
                port=self._settings.output.http_port,
                path=self._settings.output.http_path or "/stream",
            )
            if self._mjpeg_server.start():
                time.sleep(0.2)
                local_url, net_url = self._mjpeg_server.get_stream_urls()
                self._event_console.add_success(
                    f"Stream HTTP: {net_url}"
                )
                self._event_console.add_info(
                    f"Mesmo PC: {local_url} | Outros dispositivos: {net_url}"
                )
                self._event_console.add_info(
                    "ERR_CONNECTION_REFUSED? Permita o app no firewall "
                    f"(porta {self._settings.output.http_port})"
                )
            else:
                self._mjpeg_server = None
                self._event_console.add_error(
                    f"Porta {self._settings.output.http_port} em uso. "
                    "Feche outro app ou mude em Configuração → Saída."
                )

        self._update_ui_state()
        self._event_console.add_success(f"Sistema iniciado [{source_label}]")
        self._status_panel.set_system_status("RUNNING")
    
    @Slot(bool)
    def _on_model_load_finished(self, success: bool) -> None:
        """Chamado quando o carregamento do modelo termina."""
        if self._shutdown_requested:
            return
        label = self._pending_start_source_label
        self._pending_start_source_label = None
        self._play_btn.setText("▶ Iniciar")
        self._play_btn.setEnabled(True)
        if label is not None:
            if not success:
                self._event_console.add_error("Falha ao carregar modelo")
                self._stream_manager.stop()
                return
            self._event_console.add_info("Modelo carregado.")
            self._finish_start_system_after_model(label)
        else:
            self.model_preload_finished.emit(success)

    def _schedule_model_load(self, pending_start_label: Optional[str] = None) -> None:
        """
        Agenda carregamento do modelo na GUI thread.

        PyTorch (especialmente MPS no macOS) não é seguro quando o modelo é
        instanciado/movido para device numa QThread secundária.
        """
        if self._inference_engine.is_model_loaded:
            if pending_start_label is not None:
                self._finish_start_system_after_model(pending_start_label)
            else:
                self.model_preload_finished.emit(True)
            return
        if self._model_loading:
            if pending_start_label is not None:
                self._pending_start_source_label = pending_start_label
            return
        self._model_loading = True
        if pending_start_label is not None:
            self._pending_start_source_label = pending_start_label
        QTimer.singleShot(0, self._run_model_load_on_main_thread)

    def _run_model_load_on_main_thread(self) -> None:
        """Executa load_model na thread principal do Qt."""
        if not self._model_loading or self._shutdown_requested:
            self._model_loading = False
            return
        try:
            success = self._inference_engine.load_model()
        except Exception as e:
            self._logger.error("model_load_on_main_thread_failed", error=str(e))
            success = False
        self._model_loading = False
        self._on_model_load_finished(success)

    def start_model_preload(self) -> None:
        """Pré-carrega o modelo após abrir o app (na GUI thread)."""
        if self._inference_engine.is_model_loaded or self._model_loading:
            return
        self._schedule_model_load(pending_start_label=None)

    def shutdown(self) -> None:
        """Libera recursos ao fechar a aplicação."""
        self._shutdown_requested = True
        self._model_loading = False
        self._pending_start_source_label = None
        if hasattr(self, "_fps_timer"):
            self._fps_timer.stop()
        if self._is_running:
            self._stop_system()
        else:
            self._mark2.stop_worker()

    def _connect_mark2(self) -> None:
        """Inicia worker serial e conecta ao Mark2."""
        try:
            self._mark2.start_worker()
            self._mark2.connect_robot()
            mode = self._mode_combo.currentData()
            if mode:
                self._mark2.set_mode(mode)
            self._event_console.add_info("A conectar Mark2…")
            self._logger.info("mark2_connect_requested")
        except Exception as e:
            self._event_console.add_warning(f"Erro ao iniciar Mark2: {e}")
            self._logger.error("mark2_connect_exception", error=str(e))
    
    @Slot()
    def _stop_system(self) -> None:
        """Para o sistema de forma ordenada e estável."""
        if not self._is_running:
            return

        self._is_running = False

        self._event_console.add_info("Parando sistema...")

        if self._mjpeg_server is not None:
            try:
                self._mjpeg_server.stop()
            except Exception as e:
                self._logger.warning("mjpeg_stop_error", error=str(e))
            self._mjpeg_server = None

        self._mark2.stop()
        self._mark2.disconnect_robot()
        self._inference_engine.stop()
        self._stream_manager.stop()

        self._update_ui_state()
        self._pause_btn.setText("⏸ Pausar")
        self._video_widget.clear()

        self._event_console.add_info("Sistema parado")
        self._status_panel.set_system_status("STOPPED")

    @Slot()
    def _mark2_connect(self) -> None:
        """Conecta Mark2 manualmente (botão)."""
        self._mark2.start_worker()
        self._mark2.connect_robot()
        self._event_console.add_info("A conectar Mark2…", "Mark2")

    @Slot()
    def _mark2_disconnect(self) -> None:
        """Desconecta Mark2 manualmente."""
        self._mark2.disconnect_robot()
        self._event_console.add_info("Mark2 desconectado", "Mark2")
    
    @Slot()
    def _toggle_pause(self) -> None:
        """Alterna pause/resume do stream e da inferência."""
        if not self._is_running:
            return
        
        if self._stream_manager._worker and self._stream_manager._worker._paused:
            # Resumir
            self._stream_manager.resume()
            self._inference_engine.start()
            self._pause_btn.setText("⏸ Pausar")
            self._event_console.add_info("Sistema retomado")
            self._status_panel.set_system_status("RUNNING")
            self._logger.info("system_resumed")
        else:
            # Pausar
            self._stream_manager.pause()
            self._inference_engine.stop()
            self._pause_btn.setText("▶ Retomar")
            self._event_console.add_info("Sistema pausado")
            self._status_panel.set_system_status("PAUSED")
            self._logger.info("system_paused")
    
    def _update_ui_state(self) -> None:
        """Atualiza estado da UI."""
        self._play_btn.setEnabled(not self._is_running)
        self._pause_btn.setEnabled(self._is_running)
        self._stop_btn.setEnabled(self._is_running)
        self._source_combo.setEnabled(not self._is_running)
        self._source_path_btn.setEnabled(True)

        waiting_auth = (
            self._is_running
            and self._mark2.state.value == "WAITING_AUTHORIZATION"
        )
        self._authorize_send_btn.setEnabled(waiting_auth)

        if not self._is_running:
            self._status_step_label.setText("Mark2: desconectado")
            self._authorize_send_btn.setEnabled(False)
        
        self._status_panel.set_stream_running(self._is_running)
        self._status_panel.set_inference_running(self._is_running)
    
    def _on_source_changed(self, index: int) -> None:
        """Handler para mudança de fonte."""
        self._source_path_btn.setVisible(index == 0)
        self._gentl_cti_btn.setVisible(index == 3)
        self._gentl_settings_btn.setVisible(index == 3)
        self._update_source_caption()
    
    def _select_video_file(self) -> None:
        """Abre diálogo para selecionar vídeo."""
        # Obtém diretório inicial (tenta usar o último caminho ou diretório padrão)
        initial_dir = None
        current_path = self._settings.streaming.video_path
        if current_path:
            current_path_obj = Path(current_path)
            if current_path_obj.exists():
                initial_dir = str(current_path_obj.parent)
            elif current_path_obj.parent.exists():
                initial_dir = str(current_path_obj.parent)
        
        if not initial_dir:
            # Usa diretório padrão de vídeos
            base_path = Path(__file__).parent.parent.parent
            initial_dir = str(base_path / "videos")
        
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar Vídeo",
            initial_dir,
            "Vídeos (*.mp4 *.avi *.mov *.mkv);;Todos os Arquivos (*)",
        )
        
        if file_path:
            file_path_obj = Path(file_path)
            
            # Validações
            if not file_path_obj.exists():
                self._event_console.add_error(
                    f"Arquivo não encontrado: {file_path}\n"
                    f"Por favor, verifique se o arquivo existe."
                )
                return
            
            if not file_path_obj.is_file():
                self._event_console.add_error(
                    f"O caminho especificado não é um arquivo: {file_path}"
                )
                return
            
            # Testa se OpenCV consegue abrir
            import cv2
            test_cap = cv2.VideoCapture(str(file_path_obj))
            if not test_cap.isOpened():
                test_cap.release()
                self._event_console.add_error(
                    f"Não foi possível abrir o arquivo de vídeo:\n"
                    f"{file_path}\n\n"
                    f"O arquivo pode estar corrompido ou em formato não suportado.\n"
                    f"Formatos suportados: MP4, AVI, MOV, MKV"
                )
                return
            test_cap.release()
            
            # Converte para caminho absoluto normalizado
            abs_path = file_path_obj.resolve()
            abs_path_str = str(abs_path)
            
            # Atualiza configuração
            self._settings.streaming.video_path = abs_path_str
            
            # Log
            self._logger.info("video_selected", path=abs_path_str)
            self._event_console.add_info(f"Vídeo selecionado: {file_path_obj.name}")
            
            # Se o sistema está rodando, atualiza o stream sem parar a inferência
            if self._is_running and self._stream_manager.is_running:
                self._event_console.add_info("Atualizando stream para novo vídeo...")
                
                # Muda a fonte; change_source reinicia automaticamente se estava rodando
                success = self._stream_manager.change_source(
                    source_type="video",
                    video_path=abs_path_str,
                    loop_video=self._settings.streaming.loop_video,
                )
                
                if success:
                    # Atualiza o combo para refletir a nova fonte
                    self._source_combo.blockSignals(True)
                    self._source_combo.setCurrentIndex(0)  # "Arquivo de Vídeo"
                    self._source_combo.blockSignals(False)
                    self._source_path_btn.setVisible(True)
                    
                    self._event_console.add_success(f"Stream atualizado para: {file_path_obj.name}")
                    self._logger.info("video_changed_during_runtime", path=abs_path_str)
                else:
                    # O stream falhou ao trocar — para o sistema inteiro para estado consistente
                    self._event_console.add_error(
                        f"Falha ao abrir vídeo: {file_path_obj.name}\n"
                        f"O sistema será parado. Reinicie manualmente."
                    )
                    self._logger.error("video_change_failed_stopping_system", path=abs_path_str)
                    self._stop_system()
            else:
                # Sistema não está rodando, apenas atualiza configuração em memória
                self._stream_manager.change_source(
                    source_type="video",
                    video_path=abs_path_str,
                    loop_video=self._settings.streaming.loop_video,
                )
                # Atualiza o combo para refletir a nova fonte
                self._source_combo.blockSignals(True)
                self._source_combo.setCurrentIndex(0)  # "Arquivo de Vídeo"
                self._source_combo.blockSignals(False)
                self._source_path_btn.setVisible(True)
    
    def _select_gentl_cti_file(self) -> None:
        """Abre diálogo para selecionar arquivo CTI GenTL (ex.: Omron Sentech)."""
        initial_dir = None
        current_path = (self._settings.streaming.gentl_cti_path or "").strip()
        if current_path:
            current_path_obj = Path(current_path)
            if current_path_obj.exists():
                initial_dir = str(current_path_obj.parent)
            elif current_path_obj.parent.exists():
                initial_dir = str(current_path_obj.parent)
        if not initial_dir:
            initial_dir = ""  # deixa o sistema escolher (ex.: Program Files)
        
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar arquivo CTI GenTL",
            initial_dir,
            "Arquivos CTI (*.cti);;Todos os Arquivos (*)",
        )
        if file_path:
            path_obj = Path(file_path)
            if not path_obj.exists() or not path_obj.is_file():
                self._event_console.add_error(f"Arquivo não encontrado ou inválido: {file_path}")
                return
            abs_path_str = str(path_obj.resolve())
            self._settings.streaming.gentl_cti_path = abs_path_str
            self._update_source_caption()
            self._event_console.add_info(f"CTI GenTL selecionado: {path_obj.name}")
            self._logger.info("gentl_cti_selected", path=abs_path_str)

    def _open_gentl_camera_settings(self) -> None:
        """Abre a tela de ajustes da câmera GenTL (gain, exposição). Requer stream ativo."""
        adapter = self._stream_manager.get_gentl_adapter()
        if adapter is None:
            QMessageBox.information(
                self,
                "Ajustes da câmera",
                "Inicie o stream com a câmera GenTL (Omron Sentech) para poder ajustar gain, exposição e outros parâmetros.",
            )
            return
        dlg = GenTLCameraSettingsDialog(adapter, self)
        dlg.exec()
    
    def _toggle_fullscreen(self) -> None:
        """Alterna fullscreen do vídeo."""
        main_window = self.window()
        if main_window is None:
            return
        
        if main_window.isFullScreen():
            main_window.showNormal()
            self._event_console.add_info("Saiu do modo tela cheia")
        else:
            main_window.showFullScreen()
            self._event_console.add_info("Modo tela cheia (F11 para sair)")
    
    def _update_fps(self) -> None:
        """Atualiza FPS no widget de vídeo."""
        if self._stream_manager.is_running:
            fps = self._stream_manager.get_fps()
            self._video_widget.set_fps(fps)
    
    @Slot()
    def _on_stream_started(self) -> None:
        """Handler para stream iniciado."""
        self._event_console.add_info("Stream iniciado", "Stream")
    
    @Slot()
    def _on_stream_stopped(self) -> None:
        """Handler para stream parado (inclusive por falha em change_source)."""
        self._event_console.add_info("Stream parado", "Stream")
        
        # Se a UI ainda pensa que está rodando mas o stream parou,
        # precisamos sincronizar o estado para evitar inconsistência.
        if self._is_running and not self._stream_manager.is_running:
            self._logger.warning("stream_stopped_unexpectedly_resetting_state")
            self._stop_system()
    
    @Slot(str)
    def _on_stream_error(self, error: str) -> None:
        """Handler para erro de stream."""
        self._event_console.add_error(f"Erro de stream: {error}", "Stream")
    
    def _draw_roi_overlay_if_enabled(self, frame):
        """Desenha retângulo verde de marcação ROI (não corta o frame)."""
        import cv2

        enabled, coords = self._status_panel.get_roi()
        if not enabled or not coords or len(coords) != 4:
            return frame
        x, y, w, h = [int(v) for v in coords]
        h_img, w_img = frame.shape[:2]
        x1 = max(0, min(x, w_img - 1))
        y1 = max(0, min(y, h_img - 1))
        x2 = max(x1 + 1, min(x + w, w_img))
        y2 = max(y1 + 1, min(y + h, h_img))
        out = frame.copy()
        cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 0), 2)  # BGR verde, 2px
        return out

    def _draw_detections_on_frame(self, frame, result) -> np.ndarray:
        """Desenha detecções visíveis (>= display threshold) no frame MJPEG."""
        import cv2
        import math

        if result is None or not result.has_detections:
            return frame

        settings = self._settings
        display_threshold = settings.detection.display_confidence_threshold
        plc_threshold = settings.detection.plc_confidence_threshold
        mm_per_px = settings.preprocess.roi_calibration_mm_per_px or 1.0
        visible = result.visible_detections(display_threshold)
        pick_target = result.best_for_plc(plc_threshold)
        if not visible:
            return frame

        out = frame.copy()

        def _draw_one(det, is_pick: bool) -> None:
            bbox = det.bbox
            x1, y1 = int(bbox.x1), int(bbox.y1)
            x2, y2 = int(bbox.x2), int(bbox.y2)
            color = (0, 255, 0) if is_pick else (
                (0, 255, 0) if det.confidence >= 0.8 else (0, 255, 255)
            )
            thickness = 3 if is_pick else 2

            if det.has_mask and det.mask is not None:
                try:
                    bin_mask = det.mask.astype(np.uint8)
                    contours, _ = cv2.findContours(
                        bin_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE,
                    )
                    overlay = out.copy()
                    cv2.drawContours(overlay, contours, -1, color, thickness=cv2.FILLED)
                    cv2.addWeighted(overlay, 0.25, out, 0.75, 0, out)
                    cv2.drawContours(out, contours, -1, color, thickness=thickness)
                except Exception:
                    cv2.rectangle(out, (x1, y1), (x2, y2), color, thickness)
            else:
                cv2.rectangle(out, (x1, y1), (x2, y2), color, thickness)

            cx_f, cy_f = det.centroid
            cx, cy = int(cx_f), int(cy_f)
            cv2.circle(out, (cx, cy), 12 if is_pick else 10, color, 2)

            if det.has_orientation:
                angle = float(det.angle_deg or 0.0)
                half = 0.5 * float(det.major_axis_length or max(bbox.width, bbox.height))
                dx = math.cos(math.radians(angle)) * half
                dy = math.sin(math.radians(angle)) * half
                p1 = (int(cx_f - dx), int(cy_f - dy))
                p2 = (int(cx_f + dx), int(cy_f + dy))
                cv2.line(out, p1, p2, (255, 0, 255), 3)

            prefix = "PICK " if is_pick else ""
            label = f"{prefix}{det.class_name} {det.confidence:.0%}"
            cv2.putText(out, label, (x1, max(12, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            area_mm2 = (det.area_px or 0.0) * (mm_per_px ** 2)
            if area_mm2 > 0:
                cv2.putText(
                    out,
                    f"A={area_mm2:.0f}mm2",
                    (x1, y2 + 18),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (0, 255, 255),
                    2,
                )

        for det in visible:
            _draw_one(det, det is pick_target)

        return out

    @Slot(object)
    def _on_frame_available(self, frame_info) -> None:
        """Handler para frame - desenha ROI (overlay), exibe e envia para inferência."""
        if not self._is_running:
            return
        frame = frame_info.frame
        frame_for_display = self._draw_roi_overlay_if_enabled(frame)
        self._video_widget.update_frame(frame_for_display)

        if self._mjpeg_server is not None:
            result = self._inference_engine.last_result
            frame_for_stream = self._draw_detections_on_frame(frame_for_display, result)
            self._mjpeg_server.push_frame(frame_for_stream)

        if self._is_running and self._inference_engine.is_running:
            self._inference_engine.process_frame(frame, frame_info.frame_id)
    
    @Slot(object)
    def _on_detection_result(self, result) -> None:
        """Encaminha detecção ao Mark2 (calibração + FSM)."""
        if not self._is_running:
            return
        self._mark2.process_detection_result(result)

    @Slot(object)
    def _on_detection(self, event) -> None:
        """Handler para eventos de detecção — atualiza painel."""
        if not self._is_running or not event.detected:
            return
        self._detection_count += 1
        self._event_console.add_success(
            f"Detectado: {event.class_name} ({event.confidence:.0%})",
            "Detecção",
        )
        self._status_panel.update_detection(event)

    def _on_mark2_mode_changed(self, _index: int = 0) -> None:
        """Altera modo Mark2 (manual / semi / auto)."""
        mode = self._mode_combo.currentData()
        if not mode:
            return
        self._mark2.set_mode(mode)
        labels = {"manual": "Manual", "semi": "Semi", "auto": "Auto"}
        self._event_console.add_info(f"Modo Mark2: {labels.get(mode, mode)}", "Mark2")

    def _on_smoke_mode_changed(self, _state: int) -> None:
        """Ativa/desativa smoke test (detecção → motor)."""
        enabled = self._smoke_cb.isChecked()
        self._settings.mark2.operation.smoke_detection_trigger = enabled
        self._mark2.mark2.operation.smoke_detection_trigger = enabled
        label = "activado" if enabled else "desactivado"
        self._event_console.add_info(f"Teste integração (smoke) {label}", "Mark2")

    @Slot()
    def _authorize_pick(self) -> None:
        """Autoriza pick-and-place no modo semi."""
        self._mark2.authorize_pick()
        self._authorize_send_btn.setEnabled(False)
        self._event_console.add_info("Pick-and-Place autorizado pelo operador", "Mark2")

    @Slot(str)
    def _on_mark2_state_changed(self, state_value: str) -> None:
        """Actualiza botão de autorização conforme estado Mark2."""
        waiting = state_value == "WAITING_AUTHORIZATION"
        self._authorize_send_btn.setEnabled(self._is_running and waiting)

    @Slot(dict)
    def _on_mark2_coordinates(self, coords: dict) -> None:
        """Actualiza painel e overlay com coordenadas de pega."""
        self._status_panel.set_pick_and_coords(coords)
        px = coords.get("pixel")
        if px:
            self._video_widget.set_pick_point((float(px[0]), float(px[1])))

    @Slot(object)
    def _on_mark2_package_locked(self, package) -> None:
        """Objecto estável bloqueado — log no console."""
        u, v = package.pick_point_px
        self._event_console.add_info(
            f"Objecto bloqueado: pega ({u:.0f}, {v:.0f}) px",
            "Mark2",
        )

    @Slot()
    def _on_mark2_cycle_completed(self) -> None:
        """Handler para ciclo pick-and-place concluído."""
        self._event_console.add_success("Pick-and-Place concluído", "Mark2")
        self._video_widget.set_pick_point(None)

    @Slot(str)
    def _on_mark2_error(self, error: str) -> None:
        """Handler para erro Mark2."""
        self._error_count += 1
        self._event_console.add_error(f"Erro Mark2: {error}", "Mark2")
        self._status_panel.set_last_error(error)

    def _on_exit_clicked(self) -> None:
        """Fecha o sistema (mesmo fluxo do menu Arquivo → Sair)."""
        mw = self.window()
        if mw and hasattr(mw, "_confirm_and_exit"):
            mw._confirm_and_exit()
        elif mw:
            mw.close()
