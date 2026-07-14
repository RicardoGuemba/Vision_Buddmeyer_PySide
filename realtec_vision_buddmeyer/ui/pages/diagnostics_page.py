# -*- coding: utf-8 -*-
"""
Página de Diagnósticos - Métricas e logs do sistema.
"""

import platform
import sys
import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QGroupBox, QGridLayout, QLabel, QFrame,
    QPushButton, QScrollArea
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor
import torch

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False

from config import get_settings
from core.metrics import MetricsCollector
from streaming import StreamManager
from detection import InferenceEngine
from communication import CIPClient
from control import RobotController

from ui.widgets.metrics_chart import MetricsChart
from ui.widgets.log_viewer import LogViewer


class StatusCard(QFrame):
    """Card de status para visão geral."""
    
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        
        self.setStyleSheet("""
            QFrame {
                background-color: #14284c;
                border: 1px solid #1b3a69;
                border-radius: 8px;
            }
        """)
        self.setMinimumHeight(100)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        
        # Título
        self._title = QLabel(title)
        self._title.setFont(QFont("Segoe UI", 10))
        self._title.setStyleSheet("color: #c5c9ce; border: none;")
        layout.addWidget(self._title)
        
        # Valor
        self._value = QLabel("---")
        self._value.setFont(QFont("Segoe UI", 24, QFont.Bold))
        self._value.setStyleSheet("color: #26477e; border: none;")
        layout.addWidget(self._value)
        
        # Status
        self._status = QLabel("")
        self._status.setFont(QFont("Segoe UI", 9))
        self._status.setStyleSheet("color: #c5c9ce; border: none;")
        layout.addWidget(self._status)
    
    def set_value(self, value: str, color: str = "#26477e") -> None:
        """Define o valor exibido."""
        self._value.setText(value)
        self._value.setStyleSheet(f"color: {color}; border: none;")
    
    def set_status(self, status: str) -> None:
        """Define o status."""
        self._status.setText(status)


class DiagnosticsPage(QWidget):
    """
    Página de Diagnósticos.
    
    Sub-abas:
    - Visão Geral
    - Métricas
    - Logs
    - Sistema
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self._settings = get_settings()
        self._metrics = MetricsCollector()
        self._stream_manager = StreamManager()
        self._inference_engine = InferenceEngine()
        self._cip_client = CIPClient()
        self._robot_controller = RobotController()
        
        self._setup_ui()
        self._setup_timer()
    
    def _setup_ui(self) -> None:
        """Configura a interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)
        
        # Tabs
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #1b3a69;
                border-radius: 4px;
                background-color: #1e2836;
            }
            QTabBar::tab {
                background-color: #1b3a69;
                color: #e5e7eb;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #1e2836;
                color: #26477e;
            }
        """)
        
        self._tabs.addTab(self._create_overview_tab(), "Visão Geral")
        self._tabs.addTab(self._create_metrics_tab(), "Métricas")
        self._tabs.addTab(self._create_logs_tab(), "Logs")
        self._tabs.addTab(self._create_system_tab(), "Sistema")
        
        layout.addWidget(self._tabs)
    
    def _create_overview_tab(self) -> QWidget:
        """Cria aba de visão geral."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(16)
        
        # Cards de status
        cards_layout = QGridLayout()
        cards_layout.setSpacing(12)
        
        # Stream
        self._stream_card = StatusCard("Stream FPS")
        cards_layout.addWidget(self._stream_card, 0, 0)
        
        # Inferência
        self._inference_card = StatusCard("Inferência FPS")
        cards_layout.addWidget(self._inference_card, 0, 1)
        
        # Detecções
        self._detection_card = StatusCard("Detecções")
        cards_layout.addWidget(self._detection_card, 0, 2)
        
        # CLP
        self._plc_card = StatusCard("Status CLP")
        cards_layout.addWidget(self._plc_card, 1, 0)
        
        # Ciclos
        self._cycles_card = StatusCard("Ciclos")
        cards_layout.addWidget(self._cycles_card, 1, 1)
        
        # Erros
        self._errors_card = StatusCard("Erros")
        cards_layout.addWidget(self._errors_card, 1, 2)
        
        layout.addLayout(cards_layout)
        
        # Health Banner
        self._health_banner = QFrame()
        self._health_banner.setStyleSheet("""
            QFrame {
                background-color: #28a745;
                border-radius: 4px;
            }
        """)
        self._health_banner.setMinimumHeight(50)
        
        banner_layout = QHBoxLayout(self._health_banner)
        self._health_label = QLabel("✓ Sistema funcionando normalmente")
        self._health_label.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self._health_label.setStyleSheet("color: white;")
        self._health_label.setAlignment(Qt.AlignCenter)
        banner_layout.addWidget(self._health_label)
        
        layout.addWidget(self._health_banner)
        
        layout.addStretch()
        
        return widget
    
    def _create_metrics_tab(self) -> QWidget:
        """Cria aba de métricas."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)
        
        # Gráficos
        charts_layout = QGridLayout()
        charts_layout.setSpacing(12)
        
        # FPS do Stream
        self._stream_fps_chart = MetricsChart(
            "stream_fps", "FPS do Stream", "fps"
        )
        self._stream_fps_chart.set_range(0, 60)
        charts_layout.addWidget(self._stream_fps_chart, 0, 0)
        
        # Tempo de Inferência
        self._inference_time_chart = MetricsChart(
            "inference_time", "Tempo de Inferência", "ms"
        )
        self._inference_time_chart.set_color(QColor(255, 193, 7))
        charts_layout.addWidget(self._inference_time_chart, 0, 1)
        
        # Confiança de Detecção
        self._confidence_chart = MetricsChart(
            "detection_confidence", "Confiança de Detecção", "%"
        )
        self._confidence_chart.set_range(0, 100)
        self._confidence_chart.set_color(QColor(40, 167, 69))
        charts_layout.addWidget(self._confidence_chart, 1, 0)
        
        # Tempo de Resposta CIP
        self._cip_time_chart = MetricsChart(
            "cip_response_time", "Tempo de Resposta CLP", "ms"
        )
        self._cip_time_chart.set_color(QColor(220, 53, 69))
        charts_layout.addWidget(self._cip_time_chart, 1, 1)
        
        layout.addLayout(charts_layout)
        
        return widget
    
    def _create_logs_tab(self) -> QWidget:
        """Cria aba de logs."""
        return LogViewer()
    
    def _create_system_tab(self) -> QWidget:
        """Cria aba de informações do sistema."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(16)
        
        # Informações do Sistema
        sys_group = QGroupBox("Sistema Operacional")
        sys_layout = QGridLayout(sys_group)
        
        sys_layout.addWidget(QLabel("OS:"), 0, 0)
        sys_layout.addWidget(QLabel(platform.platform()), 0, 1)
        
        sys_layout.addWidget(QLabel("Python:"), 1, 0)
        sys_layout.addWidget(QLabel(sys.version.split()[0]), 1, 1)
        
        sys_layout.addWidget(QLabel("Arquitetura:"), 2, 0)
        sys_layout.addWidget(QLabel(platform.machine()), 2, 1)
        
        layout.addWidget(sys_group)
        
        # PyTorch / CUDA
        torch_group = QGroupBox("PyTorch / CUDA")
        torch_layout = QGridLayout(torch_group)
        
        torch_layout.addWidget(QLabel("PyTorch:"), 0, 0)
        torch_layout.addWidget(QLabel(torch.__version__), 0, 1)
        
        torch_layout.addWidget(QLabel("CUDA Disponível:"), 1, 0)
        cuda_available = "Sim" if torch.cuda.is_available() else "Não"
        cuda_label = QLabel(cuda_available)
        cuda_label.setStyleSheet(
            "color: #28a745;" if torch.cuda.is_available() else "color: #dc3545;"
        )
        torch_layout.addWidget(cuda_label, 1, 1)
        
        if torch.cuda.is_available():
            torch_layout.addWidget(QLabel("GPU:"), 2, 0)
            torch_layout.addWidget(QLabel(torch.cuda.get_device_name(0)), 2, 1)
            
            torch_layout.addWidget(QLabel("CUDA Version:"), 3, 0)
            torch_layout.addWidget(QLabel(torch.version.cuda or "N/A"), 3, 1)
        
        layout.addWidget(torch_group)
        
        # Modelo
        model_group = QGroupBox("Modelo de Detecção")
        model_layout = QGridLayout(model_group)
        
        model_info = self._inference_engine.get_status().get("model_info", {})
        
        model_layout.addWidget(QLabel("Carregado:"), 0, 0)
        loaded = "Sim" if model_info.get("loaded", False) else "Não"
        model_layout.addWidget(QLabel(loaded), 0, 1)
        
        model_layout.addWidget(QLabel("Nome:"), 1, 0)
        model_layout.addWidget(QLabel(model_info.get("name", "---")), 1, 1)
        
        model_layout.addWidget(QLabel("Device:"), 2, 0)
        model_layout.addWidget(QLabel(model_info.get("device", "---")), 2, 1)
        
        layout.addWidget(model_group)
        
        # Uso de Recursos
        resources_group = QGroupBox("Uso de Recursos")
        resources_layout = QGridLayout(resources_group)
        
        resources_layout.addWidget(QLabel("CPU:"), 0, 0)
        self._cpu_label = QLabel("---")
        resources_layout.addWidget(self._cpu_label, 0, 1)
        
        resources_layout.addWidget(QLabel("Memória:"), 1, 0)
        self._memory_label = QLabel("---")
        resources_layout.addWidget(self._memory_label, 1, 1)
        
        if torch.cuda.is_available():
            resources_layout.addWidget(QLabel("GPU:"), 2, 0)
            self._gpu_label = QLabel("---")
            resources_layout.addWidget(self._gpu_label, 2, 1)
        
        layout.addWidget(resources_group)
        
        layout.addStretch()
        
        scroll.setWidget(widget)
        return scroll
    
    def stop_timers(self) -> None:
        """Para timers ao encerrar a aplicação."""
        if hasattr(self, "_update_timer"):
            self._update_timer.stop()

    def _setup_timer(self) -> None:
        """Configura timer de atualização."""
        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self._update_stats)
        self._update_timer.start(1000)
    
    def _update_stats(self) -> None:
        """Atualiza estatísticas."""
        # Stream FPS
        stream_fps = self._stream_manager.get_fps() if self._stream_manager.is_running else 0
        self._stream_card.set_value(f"{stream_fps:.1f}")
        self._stream_card.set_status("Ativo" if self._stream_manager.is_running else "Parado")
        
        # Inferência
        inf_time = self._metrics.get_last_value("inference_time") or 0
        inf_fps = 1000 / inf_time if inf_time > 0 else 0
        self._inference_card.set_value(f"{inf_fps:.1f}")
        self._inference_card.set_status(f"Latência: {inf_time:.0f}ms")
        
        # Detecções
        det_count = self._metrics.get_counter("detection_count")
        self._detection_card.set_value(str(det_count))
        
        # CLP
        plc_status = self._cip_client.state.status.value
        color = "#28a745" if self._cip_client.is_connected else "#dc3545"
        self._plc_card.set_value(plc_status.upper(), color)
        
        # Ciclos
        cycle_count = self._robot_controller.cycle_count
        self._cycles_card.set_value(str(cycle_count), "#28a745")
        
        # Erros
        error_count = self._metrics.get_counter("error_count")
        error_color = "#dc3545" if error_count > 0 else "#28a745"
        self._errors_card.set_value(str(error_count), error_color)
        
        # Health
        is_healthy = (
            self._stream_manager.is_running and
            self._inference_engine.is_running and
            error_count < 10
        )
        
        if is_healthy:
            self._health_banner.setStyleSheet("QFrame { background-color: #28a745; border-radius: 4px; }")
            self._health_label.setText("✓ Sistema funcionando normalmente")
        elif self._stream_manager.is_running:
            self._health_banner.setStyleSheet("QFrame { background-color: #ffc107; border-radius: 4px; }")
            self._health_label.setText("⚠ Sistema com alertas")
        else:
            self._health_banner.setStyleSheet("QFrame { background-color: #6c757d; border-radius: 4px; }")
            self._health_label.setText("○ Sistema parado")
        
        # Recursos do sistema (aba Sistema)
        self._update_resource_usage()
    
    def _update_resource_usage(self) -> None:
        """Atualiza indicadores de uso de CPU, memória e GPU."""
        if _HAS_PSUTIL:
            try:
                # CPU do processo atual
                process = psutil.Process(os.getpid())
                cpu_percent = process.cpu_percent(interval=None)
                self._cpu_label.setText(f"{cpu_percent:.1f}%")
                
                # Memória do processo atual
                mem_info = process.memory_info()
                mem_mb = mem_info.rss / (1024 * 1024)
                self._memory_label.setText(f"{mem_mb:.0f} MB")
            except Exception:
                self._cpu_label.setText("N/A")
                self._memory_label.setText("N/A")
        else:
            self._cpu_label.setText("psutil não instalado")
            self._memory_label.setText("psutil não instalado")
        
        # GPU (via PyTorch CUDA)
        if torch.cuda.is_available() and hasattr(self, "_gpu_label"):
            try:
                allocated = torch.cuda.memory_allocated(0) / (1024 * 1024)
                reserved = torch.cuda.memory_reserved(0) / (1024 * 1024)
                self._gpu_label.setText(f"{allocated:.0f} MB alocado / {reserved:.0f} MB reservado")
            except Exception:
                self._gpu_label.setText("N/A")
