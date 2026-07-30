# -*- coding: utf-8 -*-
"""
Janela principal do sistema Buddmeyer Vision v2.0.
"""

import sys
from pathlib import Path
from datetime import datetime

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QTabWidget,
    QStatusBar, QMenuBar, QMenu, QMessageBox,
    QLabel, QFrame, QHBoxLayout
)
from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QAction, QKeySequence, QFont, QIcon

from config import get_settings
from core.logger import get_logger, setup_logging
from streaming import StreamManager
from detection import InferenceEngine

from .pages.operation_page import OperationPage
from .pages.configuration_page import ConfigurationPage
from .pages.diagnostics_page import DiagnosticsPage
from .pages.mark2_calibration_page import Mark2CalibrationPage

logger = get_logger("ui.main")


class MainWindow(QMainWindow):
    """
    Janela principal do sistema Buddmeyer Vision v2.0.
    
    Contém:
    - Menu bar
    - Tab widget com 3 abas
    - Status bar
    """
    
    def __init__(self):
        super().__init__()
        
        self._settings = get_settings()
        self._exit_in_progress = False
        
        # Singletons
        self._stream_manager = StreamManager()
        self._inference_engine = InferenceEngine()
        
        self._setup_ui()
        self._setup_menu()
        self._setup_statusbar()
        self._setup_connections()
        self._apply_theme()
        self._schedule_model_preload()
        
        logger.info("main_window_initialized")
    
    def _setup_ui(self) -> None:
        """Configura a interface."""
        self.setWindowTitle("Buddmeyer Vision System v2.0")
        self.setMinimumSize(1280, 720)
        
        # Widget central
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Tab widget
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        
        # Páginas
        self._operation_page = OperationPage()
        self._configuration_page = ConfigurationPage()
        self._diagnostics_page = DiagnosticsPage()
        self._mark2_calibration_page = Mark2CalibrationPage()

        self._tabs.addTab(self._operation_page, "🎯 Operação")
        self._tabs.addTab(self._mark2_calibration_page, "📐 Calibração Mark2")
        self._tabs.addTab(self._configuration_page, "⚙️ Configuração")
        self._tabs.addTab(self._diagnostics_page, "📊 Diagnósticos")
        self._tabs.currentChanged.connect(self._on_tab_changed)
        
        layout.addWidget(self._tabs)
    
    def _setup_menu(self) -> None:
        """Configura o menu."""
        menubar = self.menuBar()
        
        # Menu Arquivo
        file_menu = menubar.addMenu("&Arquivo")
        
        save_config_action = QAction("Salvar Configurações", self)
        save_config_action.setShortcut(QKeySequence.Save)
        save_config_action.triggered.connect(self._save_config)
        file_menu.addAction(save_config_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("Sair", self)
        exit_action.setShortcut(QKeySequence.Quit)  # Cmd+Q no macOS, Ctrl+Q no Windows
        exit_action.setShortcutContext(Qt.ApplicationShortcut)
        exit_action.triggered.connect(self._confirm_and_exit)
        file_menu.addAction(exit_action)
        
        # Menu Sistema
        system_menu = menubar.addMenu("&Sistema")
        
        start_action = QAction("Iniciar Sistema", self)
        start_action.setShortcut(QKeySequence("F5"))
        start_action.triggered.connect(self._operation_page._start_system)
        system_menu.addAction(start_action)
        
        stop_action = QAction("Parar Sistema", self)
        stop_action.setShortcut(QKeySequence("F6"))
        stop_action.triggered.connect(self._operation_page._stop_system)
        system_menu.addAction(stop_action)
        
        system_menu.addSeparator()
        
        reload_model_action = QAction("Recarregar Modelo", self)
        reload_model_action.triggered.connect(self._reload_model)
        system_menu.addAction(reload_model_action)
        
        system_menu.addSeparator()
        system_exit_action = QAction("Sair", self)
        system_exit_action.setShortcut(QKeySequence.Quit)
        system_exit_action.triggered.connect(self._confirm_and_exit)
        system_menu.addAction(system_exit_action)
        
        # Menu Ajuda
        help_menu = menubar.addMenu("A&juda")
        
        about_action = QAction("Sobre", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
    
    def _setup_statusbar(self) -> None:
        """Configura a barra de status."""
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)
        
        # Status do sistema
        self._system_status = QLabel("Sistema: Parado")
        self._system_status.setStyleSheet("color: #6c757d;")
        self._statusbar.addWidget(self._system_status)
        
        # Separador
        separator1 = QFrame()
        separator1.setFrameShape(QFrame.VLine)
        separator1.setStyleSheet("color: #3d4852;")
        self._statusbar.addWidget(separator1)
        
        # FPS
        self._fps_label = QLabel("FPS: --")
        self._fps_label.setStyleSheet("color: #17a2b8;")
        self._statusbar.addWidget(self._fps_label)
        
        # Separador
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.VLine)
        separator2.setStyleSheet("color: #3d4852;")
        self._statusbar.addWidget(separator2)
        
        # Status Mark2
        self._mark2_status = QLabel("Mark2: Desconectado")
        self._mark2_status.setStyleSheet("color: #6c757d;")
        self._statusbar.addWidget(self._mark2_status)
        
        # Espaçador
        spacer = QWidget()
        spacer.setSizePolicy(spacer.sizePolicy().horizontalPolicy(), spacer.sizePolicy().verticalPolicy())
        self._statusbar.addWidget(spacer, 1)
        
        # Timestamp
        self._timestamp_label = QLabel()
        self._statusbar.addPermanentWidget(self._timestamp_label)
        
        # Timer para atualizar status
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._update_statusbar)
        self._status_timer.start(500)
    
    def _setup_connections(self) -> None:
        """Configura conexões de sinais."""
        # Stream
        self._stream_manager.stream_started.connect(
            lambda: self._update_system_status("Rodando", "#28a745")
        )
        self._stream_manager.stream_stopped.connect(
            lambda: self._update_system_status("Parado", "#6c757d")
        )
        
        # Mark2 (via página de operação)
        mark2 = self._operation_page._mark2
        mark2.connected_changed.connect(
            lambda connected: self._update_mark2_status(
                "Conectado" if connected else "Desconectado",
                "#28a745" if connected else "#6c757d",
            )
        )
        mark2.error_occurred.connect(
            lambda err: self._update_mark2_status("Erro", "#dc3545")
        )
        
        # Pré-carregamento do modelo (página de operação)
        self._operation_page.model_preload_finished.connect(self._on_model_preload_finished)
    
    def _on_tab_changed(self, index: int) -> None:
        """Ao mudar para Operação, atualiza ROI das configurações."""
        if index == 0:  # Operação
            self._operation_page._load_roi_from_settings()
    
    def _schedule_model_preload(self) -> None:
        """Agenda o pré-carregamento do modelo 2 s após abrir a janela (evita espera ao clicar Iniciar)."""
        QTimer.singleShot(2000, self._trigger_model_preload)
    
    def _trigger_model_preload(self) -> None:
        """Inicia o carregamento do modelo em segundo plano na página de operação."""
        self._statusbar.showMessage("Preparando modelo em segundo plano...", 0)
        self._operation_page.start_model_preload()
    
    @Slot(bool)
    def _on_model_preload_finished(self, success: bool) -> None:
        """Chamado quando o pré-carregamento do modelo termina."""
        if success:
            self._statusbar.showMessage("Modelo pronto para uso.", 5000)
        else:
            self._statusbar.showMessage("Modelo será carregado ao clicar em Iniciar.", 5000)
    
    def _apply_theme(self) -> None:
        """Aplica tema RTC Integração Industrial (Manual de Marca)."""
        theme_path = Path(__file__).parent / "styles" / "industrial.qss"
        
        if theme_path.exists():
            with open(theme_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
        else:
            # Tema inline se arquivo não existir
            self.setStyleSheet("""
                QMainWindow {
                    background-color: #0d1628;
                }
                QWidget {
                    background-color: #0d1628;
                    color: #e5e7eb;
                    font-family: "Segoe UI", Arial, sans-serif;
                }
                QTabWidget::pane {
                    border: 1px solid #1b3a69;
                    background-color: #14284c;
                }
                QTabBar::tab {
                    background-color: #14284c;
                    color: #c5c9ce;
                    padding: 10px 20px;
                    border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                    margin-right: 2px;
                }
                QTabBar::tab:selected {
                    background-color: #14284c;
                    color: #26477e;
                    font-weight: bold;
                }
                QTabBar::tab:hover:!selected {
                    background-color: #1b3a69;
                }
                QMenuBar {
                    background-color: #14284c;
                    color: #e5e7eb;
                    padding: 4px;
                }
                QMenuBar::item:selected {
                    background-color: #1b3a69;
                }
                QMenu {
                    background-color: #14284c;
                    color: #e5e7eb;
                    border: 1px solid #1b3a69;
                }
                QMenu::item:selected {
                    background-color: #26477e;
                    color: #e5e7eb;
                }
                QStatusBar {
                    background-color: #14284c;
                    color: #c5c9ce;
                    border-top: 1px solid #1b3a69;
                }
                QPushButton {
                    background-color: #1b3a69;
                    color: #e5e7eb;
                    border: 1px solid #26477e;
                    padding: 6px 12px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #26477e;
                }
                QPushButton:pressed {
                    background-color: #14284c;
                }
                QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
                    background-color: #14284c;
                    color: #e5e7eb;
                    border: 1px solid #1b3a69;
                    padding: 6px;
                    border-radius: 4px;
                }
                QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
                    border-color: #26477e;
                }
                QGroupBox {
                    color: #e5e7eb;
                    border: 1px solid #1b3a69;
                    border-radius: 4px;
                    margin-top: 12px;
                    padding-top: 12px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 5px;
                }
                QScrollBar:vertical {
                    background-color: #14284c;
                    width: 12px;
                    border-radius: 6px;
                }
                QScrollBar::handle:vertical {
                    background-color: #1b3a69;
                    border-radius: 6px;
                    min-height: 20px;
                }
                QScrollBar::handle:vertical:hover {
                    background-color: #26477e;
                }
                QSlider::groove:horizontal {
                    background: #1b3a69;
                    height: 6px;
                    border-radius: 3px;
                }
                QSlider::handle:horizontal {
                    background: #26477e;
                    width: 16px;
                    height: 16px;
                    margin: -5px 0;
                    border-radius: 8px;
                }
                QCheckBox {
                    color: #e5e7eb;
                }
                QCheckBox::indicator {
                    width: 18px;
                    height: 18px;
                    border-radius: 4px;
                    border: 1px solid #1b3a69;
                    background-color: #14284c;
                }
                QCheckBox::indicator:checked {
                    background-color: #26477e;
                    border-color: #26477e;
                }
            """)
    
    def _update_statusbar(self) -> None:
        """Atualiza a barra de status."""
        # FPS
        if self._stream_manager.is_running:
            fps = self._stream_manager.get_fps()
            self._fps_label.setText(f"FPS: {fps:.1f}")
        else:
            self._fps_label.setText("FPS: --")
        
        # Timestamp
        self._timestamp_label.setText(datetime.now().strftime("%H:%M:%S"))
    
    def _update_system_status(self, status: str, color: str) -> None:
        """Atualiza status do sistema."""
        self._system_status.setText(f"Sistema: {status}")
        self._system_status.setStyleSheet(f"color: {color};")
    
    def _update_mark2_status(self, status: str, color: str) -> None:
        """Atualiza status Mark2 na barra inferior."""
        self._mark2_status.setText(f"Mark2: {status}")
        self._mark2_status.setStyleSheet(f"color: {color};")
    
    def _save_config(self) -> None:
        """Salva configurações."""
        config_path = Path(__file__).parent.parent / "config" / "config.yaml"
        self._settings.to_yaml(config_path)
        self._statusbar.showMessage("Configurações salvas!", 3000)
    
    def _reload_model(self) -> None:
        """Recarrega o modelo de detecção."""
        if self._inference_engine.is_running:
            QMessageBox.warning(
                self,
                "Aviso",
                "Pare o sistema antes de recarregar o modelo."
            )
            return
        
        self._statusbar.showMessage("Recarregando modelo...", 3000)
        
        if self._inference_engine.load_model():
            self._statusbar.showMessage("Modelo recarregado com sucesso!", 3000)
        else:
            QMessageBox.critical(
                self,
                "Erro",
                "Falha ao recarregar modelo."
            )
    
    def _show_about(self) -> None:
        """Mostra diálogo sobre."""
        QMessageBox.about(
            self,
            "Sobre Buddmeyer Vision System",
            """
            <h2>Buddmeyer Vision System v2.0</h2>
            <p>Sistema de visão computacional para automação de expedição.</p>
            <p><b>Tecnologias:</b></p>
            <ul>
                <li>PySide6 (Qt for Python)</li>
                <li>PyTorch + RT-DETR</li>
                <li>OpenCV</li>
                <li>Mark2 (Arduino serial)</li>
            </ul>
            <p><b>Plataforma:</b> macOS 12+ / Ubuntu 22.04+ / Windows 10/11</p>
            <p>© 2025 Sistema de Automação Industrial</p>
            """
        )
    
    def _is_busy_for_exit(self) -> bool:
        """True se há stream, inferência ou carregamento de modelo ativo."""
        op = self._operation_page
        return (
            op._is_running
            or op._stream_manager.is_running
            or op._inference_engine.is_running
            or getattr(op, "_model_loading", False)
        )

    def _confirm_and_exit(self) -> None:
        """Sair (menu Arquivo/Sistema, Ctrl+Q/Cmd+Q, botão Sair nas abas)."""
        if self._exit_in_progress:
            return
        if self._is_busy_for_exit():
            reply = QMessageBox.question(
                self,
                "Confirmar Saída",
                "O sistema está em execução ou carregando o modelo. Deseja parar e sair?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        self._begin_exit()

    def _begin_exit(self) -> None:
        """Shutdown unificado: timers, operação, Mark2; depois encerra o processo."""
        if self._exit_in_progress:
            return
        self._exit_in_progress = True
        if hasattr(self, "_status_timer"):
            self._status_timer.stop()
        if hasattr(self, "_diagnostics_page"):
            self._diagnostics_page.stop_timers()
        self._operation_page.shutdown()
        QTimer.singleShot(200, self._complete_exit)

    def _complete_exit(self) -> None:
        """Fecha a janela e termina o event loop Qt."""
        from PySide6.QtWidgets import QApplication

        self.hide()
        app = QApplication.instance()
        if app is not None:
            app.quit()
        else:
            self.close()

    def closeEvent(self, event) -> None:
        """Fechamento da janela (botão X ou Cmd+W)."""
        if self._exit_in_progress:
            event.accept()
            logger.info("application_closed")
            return
        if self._is_busy_for_exit():
            event.ignore()
            reply = QMessageBox.question(
                self,
                "Confirmar Saída",
                "O sistema está em execução ou carregando o modelo. Deseja parar e sair?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self._begin_exit()
            return
        self._begin_exit()
        event.ignore()
