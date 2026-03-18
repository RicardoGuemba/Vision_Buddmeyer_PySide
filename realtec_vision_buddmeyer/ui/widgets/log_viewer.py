# -*- coding: utf-8 -*-
"""
Visualizador de logs.
"""

from pathlib import Path
from datetime import datetime
from typing import List, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QPushButton, QComboBox, QLabel, QLineEdit,
    QFileDialog, QCheckBox
)
from PySide6.QtCore import Qt, Slot, QTimer, QFileSystemWatcher
from PySide6.QtGui import QFont, QTextCursor, QColor

from config import get_settings


class LogViewer(QWidget):
    """
    Visualizador de logs do sistema.
    
    Features:
    - Carrega logs de arquivo
    - Filtro por nível
    - Filtro por texto
    - Auto-refresh
    - Export
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self._settings = get_settings()
        self._log_file = Path(self._settings.log_file) if self._settings.log_file else None
        self._lines: List[str] = []
        self._filtered_lines: List[str] = []
        self._auto_refresh = True
        
        self._setup_ui()
        self._setup_watcher()
        
        # Carrega logs iniciais
        self._load_logs()
    
    def _setup_ui(self) -> None:
        """Configura a interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        
        toolbar.addWidget(QLabel("Nível:"))
        
        self._level_combo = QComboBox()
        self._level_combo.addItems(["Todos", "INFO", "WARNING", "ERROR", "DEBUG"])
        self._level_combo.currentTextChanged.connect(self._apply_filters)
        toolbar.addWidget(self._level_combo)
        
        toolbar.addWidget(QLabel("Buscar:"))
        
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Filtrar por texto...")
        self._search_input.textChanged.connect(self._apply_filters)
        toolbar.addWidget(self._search_input)
        
        toolbar.addStretch()
        
        self._auto_refresh_cb = QCheckBox("Auto-refresh")
        self._auto_refresh_cb.setChecked(True)
        self._auto_refresh_cb.stateChanged.connect(self._toggle_auto_refresh)
        toolbar.addWidget(self._auto_refresh_cb)
        
        self._refresh_btn = QPushButton("Atualizar")
        self._refresh_btn.clicked.connect(self._load_logs)
        toolbar.addWidget(self._refresh_btn)
        
        self._export_btn = QPushButton("Exportar")
        self._export_btn.clicked.connect(self._export_logs)
        toolbar.addWidget(self._export_btn)
        
        self._clear_btn = QPushButton("Limpar")
        self._clear_btn.clicked.connect(self._clear_logs)
        toolbar.addWidget(self._clear_btn)
        
        layout.addLayout(toolbar)
        
        # Viewer
        self._viewer = QTextEdit()
        self._viewer.setReadOnly(True)
        self._viewer.setFont(QFont("Consolas", 9))
        self._viewer.setStyleSheet("""
            QTextEdit {
                background-color: #14284c;
                color: #e5e7eb;
                border: 1px solid #1b3a69;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self._viewer)
        
        # Status
        self._status_label = QLabel()
        self._status_label.setStyleSheet("color: #c5c9ce;")
        layout.addWidget(self._status_label)
    
    def _setup_watcher(self) -> None:
        """Configura watcher de arquivo."""
        self._watcher = QFileSystemWatcher(self)
        
        if self._log_file and self._log_file.exists():
            self._watcher.addPath(str(self._log_file))
            self._watcher.fileChanged.connect(self._on_file_changed)
    
    def _load_logs(self) -> None:
        """Carrega logs do arquivo."""
        if not self._log_file or not self._log_file.exists():
            self._status_label.setText("Arquivo de log não encontrado")
            return
        
        try:
            with open(self._log_file, "r", encoding="utf-8") as f:
                self._lines = f.readlines()[-1000:]  # Últimas 1000 linhas
            
            self._apply_filters()
            self._status_label.setText(
                f"Carregado: {len(self._lines)} linhas | "
                f"Arquivo: {self._log_file}"
            )
            
        except Exception as e:
            self._status_label.setText(f"Erro ao carregar: {e}")
    
    def _apply_filters(self) -> None:
        """Aplica filtros e atualiza visualização."""
        level_filter = self._level_combo.currentText()
        text_filter = self._search_input.text().lower()
        
        self._filtered_lines = []
        
        for line in self._lines:
            # Filtro por nível
            if level_filter != "Todos":
                if level_filter.upper() not in line.upper():
                    continue
            
            # Filtro por texto
            if text_filter and text_filter not in line.lower():
                continue
            
            self._filtered_lines.append(line)
        
        self._update_viewer()
    
    def _update_viewer(self) -> None:
        """Atualiza o viewer com linhas filtradas."""
        self._viewer.clear()
        
        for line in self._filtered_lines:
            formatted = self._format_line(line)
            self._viewer.append(formatted)
        
        # Scroll para o final
        cursor = self._viewer.textCursor()
        cursor.movePosition(QTextCursor.End)
        self._viewer.setTextCursor(cursor)
    
    def _format_line(self, line: str) -> str:
        """Formata uma linha de log com cores."""
        line = line.strip()
        
        if "ERROR" in line.upper():
            color = "#dc3545"
        elif "WARNING" in line.upper():
            color = "#ffc107"
        elif "INFO" in line.upper():
            color = "#26477e"
        elif "DEBUG" in line.upper():
            color = "#c5c9ce"
        else:
            color = "#e5e7eb"
        
        return f'<span style="color: {color};">{line}</span>'
    
    def _on_file_changed(self, path: str) -> None:
        """Handler para mudança no arquivo."""
        if self._auto_refresh:
            self._load_logs()
        
        # Re-adiciona ao watcher (pode ser removido após modificação)
        if not self._watcher.files():
            if self._log_file and self._log_file.exists():
                self._watcher.addPath(str(self._log_file))
    
    def _toggle_auto_refresh(self, state: int) -> None:
        """Toggle auto-refresh."""
        self._auto_refresh = state == Qt.Checked
    
    def _export_logs(self) -> None:
        """Exporta logs para arquivo."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar Logs",
            f"logs_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            "Arquivos de Texto (*.txt);;Todos os Arquivos (*)",
        )
        
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.writelines(self._filtered_lines)
                self._status_label.setText(f"Exportado para: {file_path}")
            except Exception as e:
                self._status_label.setText(f"Erro ao exportar: {e}")
    
    def _clear_logs(self) -> None:
        """Limpa o viewer."""
        self._viewer.clear()
        self._lines = []
        self._filtered_lines = []
        self._status_label.setText("Logs limpos")
