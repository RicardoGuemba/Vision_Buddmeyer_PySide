# -*- coding: utf-8 -*-
"""
Página de Configuração - Configurações do sistema.
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QGroupBox, QFormLayout, QLineEdit, QSpinBox,
    QDoubleSpinBox, QComboBox, QCheckBox, QPushButton,
    QLabel, QFileDialog, QSlider, QFrame, QMessageBox
)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont

from config import get_settings
from core.logger import get_logger

logger = get_logger("config")


class ConfigurationPage(QWidget):
    """
    Página de Configuração.
    
    Sub-abas:
    - Fonte de Vídeo
    - Modelo RT-DETR
    - Pré-processamento
    - Controle (CLP)
    - Output
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self._settings = get_settings()
        self._setup_ui()
        self._load_settings()
    
    def _setup_ui(self) -> None:
        """Configura a interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)
        
        # Tabs de configuração
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #3d4852;
                border-radius: 4px;
                background-color: #1e2836;
            }
            QTabBar::tab {
                background-color: #2d3748;
                color: #e0e0e0;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #1e2836;
                color: #00d4ff;
            }
        """)
        
        # Aba Fonte de Vídeo
        self._tabs.addTab(self._create_video_tab(), "Fonte de Vídeo")
        
        # Aba Modelo
        self._tabs.addTab(self._create_model_tab(), "Modelo RT-DETR")
        
        # Aba Pré-processamento
        self._tabs.addTab(self._create_preprocess_tab(), "Pré-processamento")
        
        # Aba CLP
        self._tabs.addTab(self._create_plc_tab(), "Controle (CLP)")
        
        # Aba Output
        self._tabs.addTab(self._create_output_tab(), "Output")
        
        layout.addWidget(self._tabs)
        
        # Botões de ação
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        
        self._reset_btn = QPushButton("Restaurar Padrões")
        self._reset_btn.clicked.connect(self._reset_settings)
        buttons_layout.addWidget(self._reset_btn)
        
        self._save_btn = QPushButton("Salvar Configurações")
        self._save_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        self._save_btn.clicked.connect(self._save_settings)
        buttons_layout.addWidget(self._save_btn)
        
        layout.addLayout(buttons_layout)
    
    def _create_video_tab(self) -> QWidget:
        """Cria aba de configuração de vídeo."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(16)
        
        # Tipo de fonte
        source_group = QGroupBox("Tipo de Fonte")
        source_layout = QFormLayout(source_group)
        
        self._source_type = QComboBox()
        self._source_type.addItems([
            "Arquivo de Vídeo",
            "Câmera USB",
            "Stream RTSP",
            "Câmera GigE",
        ])
        self._source_type.currentIndexChanged.connect(self._on_source_type_changed)
        source_layout.addRow("Tipo:", self._source_type)
        
        layout.addWidget(source_group)
        
        # Arquivo de vídeo
        self._video_group = QGroupBox("Arquivo de Vídeo")
        video_layout = QFormLayout(self._video_group)
        
        path_layout = QHBoxLayout()
        self._video_path = QLineEdit()
        self._video_path.setReadOnly(True)
        path_layout.addWidget(self._video_path)
        
        browse_btn = QPushButton("Procurar...")
        browse_btn.clicked.connect(self._browse_video)
        path_layout.addWidget(browse_btn)
        video_layout.addRow("Caminho:", path_layout)
        
        self._loop_video = QCheckBox("Loop do vídeo")
        video_layout.addRow("", self._loop_video)
        
        layout.addWidget(self._video_group)
        
        # Câmera USB
        self._usb_group = QGroupBox("Câmera USB")
        usb_layout = QFormLayout(self._usb_group)
        
        self._usb_index = QSpinBox()
        self._usb_index.setRange(0, 10)
        usb_layout.addRow("Índice:", self._usb_index)
        
        layout.addWidget(self._usb_group)
        
        # RTSP
        self._rtsp_group = QGroupBox("Stream RTSP")
        rtsp_layout = QFormLayout(self._rtsp_group)
        
        self._rtsp_url = QLineEdit()
        self._rtsp_url.setPlaceholderText("rtsp://...")
        rtsp_layout.addRow("URL:", self._rtsp_url)
        
        layout.addWidget(self._rtsp_group)
        
        # GigE
        self._gige_group = QGroupBox("Câmera GigE")
        gige_layout = QFormLayout(self._gige_group)
        
        self._gige_ip = QLineEdit()
        self._gige_ip.setPlaceholderText("192.168.1.100")
        gige_layout.addRow("IP:", self._gige_ip)
        
        self._gige_port = QSpinBox()
        self._gige_port.setRange(1, 65535)
        self._gige_port.setValue(3956)
        gige_layout.addRow("Porta:", self._gige_port)
        
        layout.addWidget(self._gige_group)
        
        # Buffer
        buffer_group = QGroupBox("Buffer")
        buffer_layout = QFormLayout(buffer_group)
        
        self._buffer_size = QSpinBox()
        self._buffer_size.setRange(1, 100)
        buffer_layout.addRow("Tamanho máximo:", self._buffer_size)
        
        layout.addWidget(buffer_group)
        
        layout.addStretch()
        
        return widget
    
    def _create_model_tab(self) -> QWidget:
        """Cria aba de configuração do modelo."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(16)
        
        # Modelo
        model_group = QGroupBox("Modelo de Detecção")
        model_layout = QFormLayout(model_group)
        
        self._model_combo = QComboBox()
        self._model_combo.setEditable(True)
        self._model_combo.addItems([
            "PekingU/rtdetr_r50vd",
            "PekingU/rtdetr_r101vd",
            "facebook/detr-resnet-50",
            "facebook/detr-resnet-101",
        ])
        model_layout.addRow("Modelo:", self._model_combo)
        
        path_layout = QHBoxLayout()
        self._model_path = QLineEdit()
        path_layout.addWidget(self._model_path)
        
        browse_model_btn = QPushButton("Procurar...")
        browse_model_btn.clicked.connect(self._browse_model)
        path_layout.addWidget(browse_model_btn)
        model_layout.addRow("Caminho local:", path_layout)
        
        layout.addWidget(model_group)
        
        # Device
        device_group = QGroupBox("Processamento")
        device_layout = QFormLayout(device_group)
        
        self._device_combo = QComboBox()
        self._device_combo.addItems(["auto", "cuda", "cpu"])
        device_layout.addRow("Device:", self._device_combo)
        
        layout.addWidget(device_group)
        
        # Detecção
        detection_group = QGroupBox("Parâmetros de Detecção")
        detection_layout = QFormLayout(detection_group)
        
        # Confidence threshold
        conf_layout = QHBoxLayout()
        self._confidence_slider = QSlider(Qt.Horizontal)
        self._confidence_slider.setRange(0, 100)
        self._confidence_slider.valueChanged.connect(self._on_confidence_changed)
        conf_layout.addWidget(self._confidence_slider)
        
        self._confidence_label = QLabel("50%")
        self._confidence_label.setMinimumWidth(40)
        conf_layout.addWidget(self._confidence_label)
        detection_layout.addRow("Confiança mínima:", conf_layout)
        
        self._max_detections = QSpinBox()
        self._max_detections.setRange(1, 100)
        detection_layout.addRow("Máx. detecções:", self._max_detections)
        
        self._inference_fps = QSpinBox()
        self._inference_fps.setRange(1, 60)
        detection_layout.addRow("FPS de inferência:", self._inference_fps)
        
        layout.addWidget(detection_group)
        
        layout.addStretch()
        
        return widget
    
    def _create_preprocess_tab(self) -> QWidget:
        """Cria aba de pré-processamento."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(16)
        
        # Perfil
        profile_group = QGroupBox("Perfil")
        profile_layout = QFormLayout(profile_group)
        
        self._profile_combo = QComboBox()
        self._profile_combo.addItems([
            "default", "bright", "dark",
            "high_contrast", "low_contrast",
            "enhanced", "smooth", "sharp",
        ])
        profile_layout.addRow("Perfil:", self._profile_combo)
        
        layout.addWidget(profile_group)
        
        # Ajustes
        adjust_group = QGroupBox("Ajustes de Imagem")
        adjust_layout = QFormLayout(adjust_group)
        
        # Brilho
        brightness_layout = QHBoxLayout()
        self._brightness_slider = QSlider(Qt.Horizontal)
        self._brightness_slider.setRange(-100, 100)
        self._brightness_slider.valueChanged.connect(self._on_brightness_changed)
        brightness_layout.addWidget(self._brightness_slider)
        
        self._brightness_label = QLabel("0")
        self._brightness_label.setMinimumWidth(30)
        brightness_layout.addWidget(self._brightness_label)
        adjust_layout.addRow("Brilho:", brightness_layout)
        
        # Contraste
        contrast_layout = QHBoxLayout()
        self._contrast_slider = QSlider(Qt.Horizontal)
        self._contrast_slider.setRange(-100, 100)
        self._contrast_slider.valueChanged.connect(self._on_contrast_changed)
        contrast_layout.addWidget(self._contrast_slider)
        
        self._contrast_label = QLabel("0")
        self._contrast_label.setMinimumWidth(30)
        contrast_layout.addWidget(self._contrast_label)
        adjust_layout.addRow("Contraste:", contrast_layout)
        
        layout.addWidget(adjust_group)
        
        # ROI
        roi_group = QGroupBox("Região de Interesse (ROI)")
        roi_layout = QFormLayout(roi_group)
        
        self._roi_enabled = QCheckBox("Ativar ROI")
        roi_layout.addRow("", self._roi_enabled)
        
        roi_coords_layout = QHBoxLayout()
        self._roi_x = QSpinBox()
        self._roi_x.setRange(0, 9999)
        roi_coords_layout.addWidget(QLabel("X:"))
        roi_coords_layout.addWidget(self._roi_x)
        
        self._roi_y = QSpinBox()
        self._roi_y.setRange(0, 9999)
        roi_coords_layout.addWidget(QLabel("Y:"))
        roi_coords_layout.addWidget(self._roi_y)
        
        self._roi_w = QSpinBox()
        self._roi_w.setRange(1, 9999)
        roi_coords_layout.addWidget(QLabel("W:"))
        roi_coords_layout.addWidget(self._roi_w)
        
        self._roi_h = QSpinBox()
        self._roi_h.setRange(1, 9999)
        roi_coords_layout.addWidget(QLabel("H:"))
        roi_coords_layout.addWidget(self._roi_h)
        
        roi_layout.addRow("Coordenadas:", roi_coords_layout)
        
        layout.addWidget(roi_group)
        
        layout.addStretch()
        
        return widget
    
    def _create_plc_tab(self) -> QWidget:
        """Cria aba de configuração do CLP."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(16)
        
        # Conexão
        conn_group = QGroupBox("Conexão CIP/EtherNet-IP")
        conn_layout = QFormLayout(conn_group)
        
        self._plc_ip = QLineEdit()
        self._plc_ip.setPlaceholderText("187.99.125.5")
        conn_layout.addRow("IP do CLP:", self._plc_ip)
        
        self._plc_port = QSpinBox()
        self._plc_port.setRange(1, 65535)
        self._plc_port.setValue(44818)
        conn_layout.addRow("Porta CIP:", self._plc_port)
        
        self._conn_timeout = QDoubleSpinBox()
        self._conn_timeout.setRange(1.0, 60.0)
        self._conn_timeout.setSingleStep(0.5)
        self._conn_timeout.setSuffix(" s")
        conn_layout.addRow("Timeout:", self._conn_timeout)
        
        self._simulated = QCheckBox("Modo simulado")
        conn_layout.addRow("", self._simulated)
        
        test_btn = QPushButton("Testar Conexão")
        test_btn.clicked.connect(self._test_plc_connection)
        conn_layout.addRow("", test_btn)
        
        layout.addWidget(conn_group)
        
        # Reconexão
        retry_group = QGroupBox("Reconexão Automática")
        retry_layout = QFormLayout(retry_group)
        
        self._retry_interval = QDoubleSpinBox()
        self._retry_interval.setRange(0.5, 30.0)
        self._retry_interval.setSingleStep(0.5)
        self._retry_interval.setSuffix(" s")
        retry_layout.addRow("Intervalo:", self._retry_interval)
        
        self._max_retries = QSpinBox()
        self._max_retries.setRange(0, 100)
        retry_layout.addRow("Máx. tentativas:", self._max_retries)
        
        layout.addWidget(retry_group)
        
        # Heartbeat
        hb_group = QGroupBox("Heartbeat")
        hb_layout = QFormLayout(hb_group)
        
        self._heartbeat_interval = QDoubleSpinBox()
        self._heartbeat_interval.setRange(0.1, 10.0)
        self._heartbeat_interval.setSingleStep(0.1)
        self._heartbeat_interval.setSuffix(" s")
        hb_layout.addRow("Intervalo:", self._heartbeat_interval)
        
        layout.addWidget(hb_group)
        
        layout.addStretch()
        
        return widget
    
    def _create_output_tab(self) -> QWidget:
        """Cria aba de configuração de output."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(16)
        
        # RTSP Server
        rtsp_group = QGroupBox("Servidor RTSP")
        rtsp_layout = QFormLayout(rtsp_group)
        
        self._rtsp_enabled = QCheckBox("Habilitar servidor RTSP")
        rtsp_layout.addRow("", self._rtsp_enabled)
        
        self._rtsp_port = QSpinBox()
        self._rtsp_port.setRange(1, 65535)
        self._rtsp_port.setValue(8554)
        rtsp_layout.addRow("Porta:", self._rtsp_port)
        
        self._rtsp_path = QLineEdit()
        self._rtsp_path.setText("/stream")
        rtsp_layout.addRow("Path:", self._rtsp_path)
        
        layout.addWidget(rtsp_group)
        
        layout.addStretch()
        
        return widget
    
    def _load_settings(self) -> None:
        """Carrega configurações atuais."""
        s = self._settings
        
        # Vídeo
        source_map = {"video": 0, "usb": 1, "rtsp": 2, "gige": 3}
        self._source_type.setCurrentIndex(source_map.get(s.streaming.source_type, 0))
        self._video_path.setText(s.streaming.video_path)
        self._loop_video.setChecked(s.streaming.loop_video)
        self._usb_index.setValue(s.streaming.usb_camera_index)
        self._rtsp_url.setText(s.streaming.rtsp_url)
        self._gige_ip.setText(s.streaming.gige_ip)
        self._gige_port.setValue(s.streaming.gige_port)
        self._buffer_size.setValue(s.streaming.max_frame_buffer_size)
        
        # Modelo
        self._model_combo.setCurrentText(s.detection.default_model)
        self._model_path.setText(s.detection.model_path)
        self._device_combo.setCurrentText(s.detection.device)
        self._confidence_slider.setValue(int(s.detection.confidence_threshold * 100))
        self._max_detections.setValue(s.detection.max_detections)
        self._inference_fps.setValue(s.detection.inference_fps)
        
        # Pré-processamento
        self._profile_combo.setCurrentText(s.preprocess.profile)
        self._brightness_slider.setValue(int(s.preprocess.brightness * 100))
        self._contrast_slider.setValue(int(s.preprocess.contrast * 100))
        
        # CLP
        self._plc_ip.setText(s.cip.ip)
        self._plc_port.setValue(s.cip.port)
        self._conn_timeout.setValue(s.cip.connection_timeout)
        self._simulated.setChecked(s.cip.simulated)
        self._retry_interval.setValue(s.cip.retry_interval)
        self._max_retries.setValue(s.cip.max_retries)
        self._heartbeat_interval.setValue(s.cip.heartbeat_interval)
        
        # Output
        self._rtsp_enabled.setChecked(s.output.rtsp_enabled)
        self._rtsp_port.setValue(s.output.rtsp_port)
        self._rtsp_path.setText(s.output.rtsp_path)
        
        self._on_source_type_changed(self._source_type.currentIndex())
    
    def _save_settings(self) -> None:
        """Salva configurações."""
        s = self._settings
        
        # Vídeo
        source_types = ["video", "usb", "rtsp", "gige"]
        s.streaming.source_type = source_types[self._source_type.currentIndex()]
        s.streaming.video_path = self._video_path.text()
        s.streaming.loop_video = self._loop_video.isChecked()
        s.streaming.usb_camera_index = self._usb_index.value()
        s.streaming.rtsp_url = self._rtsp_url.text()
        s.streaming.gige_ip = self._gige_ip.text()
        s.streaming.gige_port = self._gige_port.value()
        s.streaming.max_frame_buffer_size = self._buffer_size.value()
        
        # Modelo
        s.detection.default_model = self._model_combo.currentText()
        s.detection.model_path = self._model_path.text()
        s.detection.device = self._device_combo.currentText()
        s.detection.confidence_threshold = self._confidence_slider.value() / 100
        s.detection.max_detections = self._max_detections.value()
        s.detection.inference_fps = self._inference_fps.value()
        
        # Pré-processamento
        s.preprocess.profile = self._profile_combo.currentText()
        s.preprocess.brightness = self._brightness_slider.value() / 100
        s.preprocess.contrast = self._contrast_slider.value() / 100
        
        # CLP
        s.cip.ip = self._plc_ip.text()
        s.cip.port = self._plc_port.value()
        s.cip.connection_timeout = self._conn_timeout.value()
        s.cip.simulated = self._simulated.isChecked()
        s.cip.retry_interval = self._retry_interval.value()
        s.cip.max_retries = self._max_retries.value()
        s.cip.heartbeat_interval = self._heartbeat_interval.value()
        
        # Output
        s.output.rtsp_enabled = self._rtsp_enabled.isChecked()
        s.output.rtsp_port = self._rtsp_port.value()
        s.output.rtsp_path = self._rtsp_path.text()
        
        # Salva em arquivo
        config_path = Path(__file__).parent.parent.parent / "config" / "config.yaml"
        s.to_yaml(config_path)
        
        logger.info(
            "config_saved",
            cip_ip=s.cip.ip,
            cip_port=s.cip.port,
            config_path=str(config_path),
        )
        
        QMessageBox.information(self, "Sucesso", "Configurações salvas com sucesso!")
    
    def _reset_settings(self) -> None:
        """Restaura configurações padrão."""
        # TODO: Implementar reset
        QMessageBox.information(self, "Info", "Reset não implementado")
    
    def _browse_video(self) -> None:
        """Abre diálogo para selecionar vídeo."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar Vídeo",
            "",
            "Vídeos (*.mp4 *.avi *.mov *.mkv);;Todos (*)",
        )
        if file_path:
            self._video_path.setText(file_path)
    
    def _browse_model(self) -> None:
        """Abre diálogo para selecionar modelo."""
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "Selecionar Diretório do Modelo",
        )
        if dir_path:
            self._model_path.setText(dir_path)
    
    def _on_source_type_changed(self, index: int) -> None:
        """Handler para mudança de tipo de fonte."""
        self._video_group.setVisible(index == 0)
        self._usb_group.setVisible(index == 1)
        self._rtsp_group.setVisible(index == 2)
        self._gige_group.setVisible(index == 3)
    
    def _on_confidence_changed(self, value: int) -> None:
        """Handler para mudança de confiança."""
        self._confidence_label.setText(f"{value}%")
    
    def _on_brightness_changed(self, value: int) -> None:
        """Handler para mudança de brilho."""
        self._brightness_label.setText(str(value))
    
    def _on_contrast_changed(self, value: int) -> None:
        """Handler para mudança de contraste."""
        self._contrast_label.setText(str(value))
    
    def _test_plc_connection(self) -> None:
        """Testa conexão com CLP."""
        # TODO: Implementar teste de conexão
        QMessageBox.information(self, "Info", "Teste não implementado")
