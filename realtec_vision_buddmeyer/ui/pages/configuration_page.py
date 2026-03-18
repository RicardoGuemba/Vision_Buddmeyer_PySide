# -*- coding: utf-8 -*-
"""
Página de Configuração - Configurações do sistema.
Interface reformulada: agrupamento por função, layout estado da arte (ISA-101).
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QGroupBox, QFormLayout, QLineEdit, QSpinBox,
    QDoubleSpinBox, QComboBox, QCheckBox, QPushButton,
    QLabel, QFileDialog, QSlider, QFrame, QMessageBox,
    QScrollArea, QGridLayout, QApplication
)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont

from config import get_settings
from core.logger import get_logger
from streaming.mjpeg_server import get_local_ip

logger = get_logger("config")


# Estilos ISA-101 / HMI industrial (pick-and-place)
CONFIG_GROUP_STYLE = """
    QGroupBox {
        font-weight: bold;
        color: #e0e0e0;
        border: 1px solid #3d4852;
        border-radius: 6px;
        margin-top: 14px;
        padding: 12px 12px 12px 12px;
        background-color: #1a2332;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 6px;
        color: #00d4ff;
    }
"""


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
        """Configura a interface (ISA-101: ações primárias no topo)."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)
        
        # Barra de ações (ISA-101: ações no topo para visibilidade imediata)
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        self._reset_btn = QPushButton("Restaurar Padrões")
        self._reset_btn.setToolTip("Restaura valores padrão (não persiste até Salvar)")
        self._reset_btn.clicked.connect(self._reset_settings)
        buttons_layout.addWidget(self._reset_btn)
        self._save_btn = QPushButton("Salvar Configurações")
        self._save_btn.setToolTip("Persiste configurações no arquivo config.yaml")
        self._save_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-weight: bold;
                padding: 10px 20px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        self._save_btn.clicked.connect(self._save_settings)
        buttons_layout.addWidget(self._save_btn)
        self._exit_btn = QPushButton("Sair")
        self._exit_btn.setToolTip("Encerra o sistema (Cmd+Q no macOS)")
        self._exit_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                padding: 10px 20px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        self._exit_btn.clicked.connect(self._on_exit_clicked)
        buttons_layout.addWidget(self._exit_btn)
        layout.addLayout(buttons_layout)
        
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
        
        # Abas agrupadas por função (estado da arte)
        self._tabs.addTab(self._create_entrada_tab(), "Entrada")
        self._tabs.addTab(self._create_deteccao_tab(), "Detecção")
        self._tabs.addTab(self._create_imagem_tab(), "Imagem")
        self._tabs.addTab(self._create_plc_tab(), "CLP")
        self._tabs.addTab(self._create_output_tab(), "Saída")
        
        layout.addWidget(self._tabs)
    
    def _on_exit_clicked(self) -> None:
        """Fecha o sistema (mesmo fluxo do menu Arquivo → Sair)."""
        mw = self.window()
        if mw and hasattr(mw, "_confirm_and_exit"):
            mw._confirm_and_exit()
        else:
            mw.close() if mw else None
    
    def _create_entrada_tab(self) -> QWidget:
        """Aba Entrada: fontes de vídeo e buffer."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(20)
        
        # Parâmetros de cada fonte (tipo definido na aba Operação)
        self._video_group = QGroupBox("Arquivo de Vídeo")
        self._video_group.setStyleSheet(CONFIG_GROUP_STYLE)
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
        
        self._usb_group = QGroupBox("Câmera USB")
        self._usb_group.setStyleSheet(CONFIG_GROUP_STYLE)
        usb_layout = QFormLayout(self._usb_group)
        
        self._usb_index = QSpinBox()
        self._usb_index.setRange(0, 10)
        usb_layout.addRow("Índice:", self._usb_index)
        
        layout.addWidget(self._usb_group)
        
        self._gige_group = QGroupBox("Câmera GigE")
        self._gige_group.setStyleSheet(CONFIG_GROUP_STYLE)
        gige_layout = QFormLayout(self._gige_group)
        
        self._gige_ip = QLineEdit()
        self._gige_ip.setPlaceholderText("192.168.1.100")
        gige_layout.addRow("IP:", self._gige_ip)
        
        self._gige_port = QSpinBox()
        self._gige_port.setRange(1, 65535)
        self._gige_port.setValue(3956)
        gige_layout.addRow("Porta:", self._gige_port)
        
        layout.addWidget(self._gige_group)
        
        self._gentl_group = QGroupBox("Câmera GenTL (Omron Sentech)")
        self._gentl_group.setStyleSheet(CONFIG_GROUP_STYLE)
        gentl_layout = QFormLayout(self._gentl_group)
        
        cti_layout = QHBoxLayout()
        self._gentl_cti_path = QLineEdit()
        self._gentl_cti_path.setPlaceholderText(r"C:\...\StGenTL_MD_VC141_v1_5_x64.cti")
        self._gentl_cti_path.setReadOnly(True)
        cti_layout.addWidget(self._gentl_cti_path)
        
        gentl_browse_btn = QPushButton("Procurar...")
        gentl_browse_btn.clicked.connect(self._browse_gentl_cti)
        cti_layout.addWidget(gentl_browse_btn)
        gentl_layout.addRow("Arquivo CTI:", cti_layout)
        
        self._gentl_device_index = QSpinBox()
        self._gentl_device_index.setRange(0, 10)
        self._gentl_device_index.setToolTip("Índice da câmera na lista GenTL (0 = primeira)")
        gentl_layout.addRow("Índice da câmera:", self._gentl_device_index)
        
        self._gentl_max_dimension = QSpinBox()
        self._gentl_max_dimension.setRange(0, 4096)
        self._gentl_max_dimension.setValue(1920)
        self._gentl_max_dimension.setSpecialValueText("Sem limite")
        self._gentl_max_dimension.setToolTip("Máximo do lado maior em pixels (0 = não redimensionar). Reduz carga em câmeras 20MP+.")
        gentl_layout.addRow("Dimensão máx. (px):", self._gentl_max_dimension)
        
        self._gentl_target_fps = QDoubleSpinBox()
        self._gentl_target_fps.setRange(1.0, 60.0)
        self._gentl_target_fps.setValue(15.0)
        self._gentl_target_fps.setDecimals(1)
        self._gentl_target_fps.setToolTip("FPS alvo do stream (valores menores reduzem carga em alta resolução)")
        gentl_layout.addRow("FPS alvo:", self._gentl_target_fps)
        
        layout.addWidget(self._gentl_group)
        
        buffer_group = QGroupBox("Buffer de Frames")
        buffer_group.setStyleSheet(CONFIG_GROUP_STYLE)
        buffer_layout = QFormLayout(buffer_group)
        
        self._buffer_size = QSpinBox()
        self._buffer_size.setRange(1, 100)
        buffer_layout.addRow("Tamanho máximo:", self._buffer_size)
        
        layout.addWidget(buffer_group)
        
        layout.addStretch()
        scroll.setWidget(widget)
        return scroll
    
    def _create_deteccao_tab(self) -> QWidget:
        """Aba Detecção: modelo, processamento e pré-processamento."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(16)
        
        model_group = QGroupBox("Modelo")
        model_group.setStyleSheet(CONFIG_GROUP_STYLE)
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
        
        params_group = QGroupBox("Parâmetros")
        params_group.setStyleSheet(CONFIG_GROUP_STYLE)
        params_layout = QFormLayout(params_group)
        self._device_combo = QComboBox()
        self._device_combo.addItems(["auto", "cuda", "mps", "cpu"])
        params_layout.addRow("Device:", self._device_combo)
        conf_layout = QHBoxLayout()
        self._confidence_slider = QSlider(Qt.Horizontal)
        self._confidence_slider.setRange(0, 100)
        self._confidence_slider.valueChanged.connect(self._on_confidence_changed)
        conf_layout.addWidget(self._confidence_slider)
        self._confidence_label = QLabel("50%")
        self._confidence_label.setMinimumWidth(40)
        conf_layout.addWidget(self._confidence_label)
        params_layout.addRow("Confiança mín.:", conf_layout)
        self._max_detections = QSpinBox()
        self._max_detections.setRange(1, 100)
        params_layout.addRow("Máx. detecções:", self._max_detections)
        self._inference_fps = QSpinBox()
        self._inference_fps.setRange(1, 60)
        params_layout.addRow("FPS inferência:", self._inference_fps)
        layout.addWidget(params_group)
        layout.addStretch()
        return widget
    
    def _create_imagem_tab(self) -> QWidget:
        """Aba Imagem: ROI e perfil de pré-processamento."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(16)
        
        roi_group = QGroupBox("ROI (Região de Interesse)")
        roi_group.setStyleSheet(CONFIG_GROUP_STYLE)
        roi_group.setToolTip("Define a região da imagem usada na detecção. Sempre em pixels.")
        roi_layout = QFormLayout(roi_group)

        roi_coords = QHBoxLayout()
        self._roi_x = QDoubleSpinBox()
        self._roi_x.setRange(0, 9999)
        self._roi_x.setDecimals(1)
        self._roi_x.setToolTip("Coordenada X do canto superior esquerdo")
        self._roi_y = QDoubleSpinBox()
        self._roi_y.setRange(0, 9999)
        self._roi_y.setDecimals(1)
        self._roi_y.setToolTip("Coordenada Y do canto superior esquerdo")
        self._roi_w = QDoubleSpinBox()
        self._roi_w.setRange(0.1, 9999)
        self._roi_w.setDecimals(1)
        self._roi_w.setToolTip("Largura da região")
        self._roi_h = QDoubleSpinBox()
        self._roi_h.setRange(0.1, 9999)
        self._roi_h.setDecimals(1)
        self._roi_h.setToolTip("Altura da região")
        roi_coords.addWidget(QLabel("X:"))
        roi_coords.addWidget(self._roi_x)
        roi_coords.addWidget(QLabel("Y:"))
        roi_coords.addWidget(self._roi_y)
        roi_coords.addWidget(QLabel("W:"))
        roi_coords.addWidget(self._roi_w)
        roi_coords.addWidget(QLabel("H:"))
        roi_coords.addWidget(self._roi_h)
        roi_layout.addRow("Coordenadas (x, y, largura, altura) [px]:", roi_coords)

        roi_default_btn = QPushButton("Padrão (25% área central)")
        roi_default_btn.setToolTip("Define ROI como 25% da área centralizada (ex.: 640x480)")
        roi_default_btn.clicked.connect(self._set_default_roi)
        roi_layout.addRow("", roi_default_btn)

        self._centroid_mm_per_px = QDoubleSpinBox()
        self._centroid_mm_per_px.setRange(0.0001, 10000.0)
        self._centroid_mm_per_px.setValue(1.0)
        self._centroid_mm_per_px.setSuffix(" mm/px")
        self._centroid_mm_per_px.setToolTip(
            "Relação mm/px aplicada ao centroide (X,Y) da detecção. Default 1. Ex.: 100 → coord_mm = px * 100"
        )
        roi_layout.addRow("Centroide (mm/px):", self._centroid_mm_per_px)

        layout.addWidget(roi_group)
        
        profile_group = QGroupBox("Perfil de Imagem")
        profile_group.setStyleSheet(CONFIG_GROUP_STYLE)
        profile_layout = QFormLayout(profile_group)
        self._profile_combo = QComboBox()
        self._profile_combo.addItems([
            "default", "bright", "dark",
            "high_contrast", "low_contrast",
            "enhanced", "smooth", "sharp",
        ])
        profile_layout.addRow("Perfil:", self._profile_combo)
        layout.addWidget(profile_group)
        layout.addStretch()
        return widget
    
    def _set_default_roi(self) -> None:
        """Aplica ROI padrão (25% da área centralizada) em pixels."""
        from config.settings import DEFAULT_ROI_QUARTER_AREA
        x, y, w, h = DEFAULT_ROI_QUARTER_AREA
        self._roi_x.setValue(x)
        self._roi_y.setValue(y)
        self._roi_w.setValue(w)
        self._roi_h.setValue(h)
    
    def _create_plc_tab(self) -> QWidget:
        """Cria aba de configuração do CLP."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(16)
        
        conn_group = QGroupBox("Conexão CIP/EtherNet-IP")
        conn_group.setStyleSheet(CONFIG_GROUP_STYLE)
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
        
        retry_group = QGroupBox("Reconexão Automática")
        retry_group.setStyleSheet(CONFIG_GROUP_STYLE)
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
        
        hb_group = QGroupBox("Heartbeat")
        hb_group.setStyleSheet(CONFIG_GROUP_STYLE)
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
        """Aba Saída: servidor HTTP MJPEG – copie a URL e cole no navegador."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(16)
        
        stream_group = QGroupBox("Stream HTTP (MJPEG)")
        stream_group.setStyleSheet(CONFIG_GROUP_STYLE)
        stream_layout = QFormLayout(stream_group)
        
        self._rtsp_enabled = QCheckBox("Habilitar stream para navegador")
        stream_layout.addRow("", self._rtsp_enabled)
        
        self._http_port = QSpinBox()
        self._http_port.setRange(1, 65535)
        self._http_port.setValue(8080)
        stream_layout.addRow("Porta:", self._http_port)
        
        copy_btn = QPushButton("Copiar URL")
        copy_btn.setToolTip("Copia a URL para a área de transferência. Cole na barra de endereços do navegador.")
        copy_btn.clicked.connect(self._copy_stream_url)
        stream_layout.addRow("", copy_btn)
        
        url_help = QLabel(
            "Clique em 'Copiar URL' e cole na barra de endereços do Chrome, Firefox ou Edge."
        )
        url_help.setStyleSheet("color: #8b9dc3; font-size: 11px;")
        url_help.setWordWrap(True)
        stream_layout.addRow("", url_help)
        
        layout.addWidget(stream_group)
        layout.addStretch()
        
        return widget
    
    def _get_stream_url(self) -> str:
        """Retorna a URL do stream HTTP (IP:porta/stream)."""
        port = self._http_port.value()
        host = get_local_ip()
        return f"http://{host}:{port}/stream"

    def _copy_stream_url(self) -> None:
        """Copia a URL HTTP para a área de transferência."""
        url = self._get_stream_url()
        clipboard = QApplication.clipboard()
        clipboard.setText(url)
        QMessageBox.information(
            self, "Copiado",
            f"URL copiada para a área de transferência:\n{url}\n\nCole na barra de endereços do navegador."
        )
    
    def _load_settings(self) -> None:
        """Carrega configurações atuais."""
        s = self._settings
        
        # Vídeo (tipo definido na aba Operação)
        self._video_path.setText(s.streaming.video_path)
        self._loop_video.setChecked(s.streaming.loop_video)
        self._usb_index.setValue(s.streaming.usb_camera_index)
        self._gige_ip.setText(s.streaming.gige_ip)
        self._gige_port.setValue(s.streaming.gige_port)
        self._gentl_cti_path.setText(s.streaming.gentl_cti_path)
        self._gentl_device_index.setValue(s.streaming.gentl_device_index)
        self._gentl_max_dimension.setValue(s.streaming.gentl_max_dimension)
        self._gentl_target_fps.setValue(s.streaming.gentl_target_fps)
        self._buffer_size.setValue(s.streaming.max_frame_buffer_size)
        
        # Modelo
        self._model_combo.setCurrentText(s.detection.default_model)
        self._model_path.setText(s.detection.model_path)
        self._device_combo.setCurrentText(s.detection.device)
        self._confidence_slider.setValue(int(s.detection.confidence_threshold * 100))
        self._max_detections.setValue(s.detection.max_detections)
        self._inference_fps.setValue(s.detection.inference_fps)
        
        # Imagem (ROI em px, calibração centroide mm/px)
        if s.preprocess.roi and len(s.preprocess.roi) == 4:
            px_vals = [float(s.preprocess.roi[i]) for i in range(4)]
        else:
            from config.settings import DEFAULT_ROI_QUARTER_AREA
            px_vals = list(DEFAULT_ROI_QUARTER_AREA)

        self._roi_x.setValue(px_vals[0])
        self._roi_y.setValue(px_vals[1])
        self._roi_w.setValue(px_vals[2])
        self._roi_h.setValue(px_vals[3])
        self._centroid_mm_per_px.setValue(
            getattr(s.preprocess, "roi_calibration_mm_per_px", 1.0)
        )
        self._profile_combo.setCurrentText(s.preprocess.profile)
        
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
        self._http_port.setValue(s.output.http_port)
    
    def _save_settings(self) -> None:
        """Salva configurações."""
        s = self._settings
        
        # Vídeo (source_type definido na aba Operação)
        s.streaming.video_path = self._video_path.text()
        s.streaming.loop_video = self._loop_video.isChecked()
        s.streaming.usb_camera_index = self._usb_index.value()
        s.streaming.gige_ip = self._gige_ip.text()
        s.streaming.gige_port = self._gige_port.value()
        s.streaming.gentl_cti_path = self._gentl_cti_path.text()
        s.streaming.gentl_device_index = self._gentl_device_index.value()
        s.streaming.gentl_max_dimension = self._gentl_max_dimension.value()
        s.streaming.gentl_target_fps = self._gentl_target_fps.value()
        s.streaming.max_frame_buffer_size = self._buffer_size.value()
        
        # Modelo
        s.detection.default_model = self._model_combo.currentText()
        s.detection.model_path = self._model_path.text()
        s.detection.device = self._device_combo.currentText()
        s.detection.confidence_threshold = self._confidence_slider.value() / 100
        s.detection.max_detections = self._max_detections.value()
        s.detection.inference_fps = self._inference_fps.value()
        
        # Imagem (ROI em px, calibração centroide mm/px)
        px_vals = [
            int(round(self._roi_x.value())),
            int(round(self._roi_y.value())),
            max(1, int(round(self._roi_w.value()))),
            max(1, int(round(self._roi_h.value()))),
        ]
        s.preprocess.roi = px_vals
        s.preprocess.roi_calibration_mm_per_px = self._centroid_mm_per_px.value()
        s.preprocess.profile = self._profile_combo.currentText()
        
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
        s.output.http_port = self._http_port.value()
        s.output.http_path = "/stream"
        
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
        """Restaura configurações padrão carregando valores default do Pydantic."""
        reply = QMessageBox.question(
            self,
            "Confirmar Reset",
            "Restaurar todas as configurações para os valores padrão?\n"
            "As configurações atuais serão perdidas.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        
        from config.settings import (
            StreamingSettings, DetectionSettings, PreprocessSettings,
            CIPSettings, OutputSettings,
        )
        
        # Aplica defaults no objeto settings em memória
        s = self._settings
        s.streaming = StreamingSettings()
        s.detection = DetectionSettings()
        s.preprocess = PreprocessSettings()
        s.cip = CIPSettings()
        s.output = OutputSettings()
        
        # Recarrega a UI com os novos valores
        self._load_settings()
        
        logger.info("settings_reset_to_defaults")
        QMessageBox.information(
            self, "Sucesso",
            "Configurações restauradas aos valores padrão.\n"
            "Clique em 'Salvar Configurações' para persistir no arquivo."
        )
    
    def _browse_gentl_cti(self) -> None:
        """Abre diálogo para selecionar arquivo CTI GenTL."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar arquivo CTI GenTL",
            "",
            "Arquivos CTI (*.cti);;Todos (*)",
        )
        if file_path:
            self._gentl_cti_path.setText(file_path)
    
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
    
    def _on_confidence_changed(self, value: int) -> None:
        """Handler para mudança de confiança."""
        self._confidence_label.setText(f"{value}%")
    
    def _test_plc_connection(self) -> None:
        """Testa conexão com CLP usando os parâmetros atuais da UI."""
        ip = self._plc_ip.text().strip()
        port = self._plc_port.value()
        timeout = self._conn_timeout.value()
        simulated = self._simulated.isChecked()
        
        if simulated:
            QMessageBox.information(
                self, "Modo Simulado",
                "O modo simulado está ativado.\n"
                "Desmarque 'Modo simulado' para testar a conexão real com o CLP."
            )
            return
        
        if not ip:
            QMessageBox.warning(self, "Aviso", "Informe o IP do CLP.")
            return
        
        # Teste de alcance via socket (não depende do CIP completo)
        import socket
        
        QMessageBox.information(
            self, "Testando...",
            f"Testando conexão TCP com {ip}:{port}...\n"
            f"Timeout: {timeout}s"
        )
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((ip, port))
            sock.close()
            
            if result == 0:
                QMessageBox.information(
                    self, "Sucesso",
                    f"Conexão TCP com {ip}:{port} estabelecida com sucesso.\n"
                    f"O CLP está acessível na rede."
                )
                logger.info("plc_connection_test_success", ip=ip, port=port)
            else:
                QMessageBox.warning(
                    self, "Falha",
                    f"Não foi possível conectar a {ip}:{port}.\n"
                    f"Código de erro: {result}\n\n"
                    f"Verifique:\n"
                    f"- O CLP está ligado e na rede?\n"
                    f"- O IP e porta estão corretos?\n"
                    f"- Há firewall bloqueando a porta?"
                )
                logger.warning("plc_connection_test_failed", ip=ip, port=port, error_code=result)
        except socket.timeout:
            QMessageBox.warning(
                self, "Timeout",
                f"Timeout ao conectar a {ip}:{port} ({timeout}s).\n"
                f"O CLP não respondeu no tempo esperado."
            )
            logger.warning("plc_connection_test_timeout", ip=ip, port=port)
        except Exception as e:
            QMessageBox.critical(
                self, "Erro",
                f"Erro ao testar conexão: {e}"
            )
            logger.error("plc_connection_test_error", ip=ip, port=port, error=str(e))
