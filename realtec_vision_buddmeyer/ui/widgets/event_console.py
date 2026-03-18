# -*- coding: utf-8 -*-
"""
Console de eventos em tempo real.
"""

from datetime import datetime
from typing import List
from dataclasses import dataclass
from enum import Enum

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QPushButton, QComboBox, QLabel
)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont, QTextCursor, QColor


class EventLevel(str, Enum):
    """Nível do evento."""
    
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"
    DEBUG = "DEBUG"


@dataclass
class EventEntry:
    """Entrada de evento."""
    
    timestamp: datetime
    level: EventLevel
    message: str
    source: str = ""
    
    def format_html(self) -> str:
        """Formata como HTML."""
        colors = {
            EventLevel.INFO: "#26477e",
            EventLevel.SUCCESS: "#28a745",
            EventLevel.WARNING: "#ffc107",
            EventLevel.ERROR: "#dc3545",
            EventLevel.DEBUG: "#c5c9ce",
        }
        
        color = colors.get(self.level, "#ffffff")
        time_str = self.timestamp.strftime("%H:%M:%S.%f")[:-3]
        source_str = f"[{self.source}] " if self.source else ""
        
        return (
            f'<span style="color: #c5c9ce;">{time_str}</span> '
            f'<span style="color: {color}; font-weight: bold;">[{self.level.value}]</span> '
            f'<span style="color: #c5c9ce;">{source_str}</span>'
            f'<span style="color: #e5e7eb;">{self.message}</span>'
        )


class EventConsole(QWidget):
    """
    Console de eventos em tempo real.
    
    Exibe eventos do sistema com cores por nível.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self._events: List[EventEntry] = []
        self._max_events = 500
        self._filter_level: EventLevel = None
        self._auto_scroll = True
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Configura a interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        
        toolbar.addWidget(QLabel("Filtrar:"))
        
        self._filter_combo = QComboBox()
        self._filter_combo.addItem("Todos", None)
        self._filter_combo.addItem("Info", EventLevel.INFO)
        self._filter_combo.addItem("Sucesso", EventLevel.SUCCESS)
        self._filter_combo.addItem("Aviso", EventLevel.WARNING)
        self._filter_combo.addItem("Erro", EventLevel.ERROR)
        self._filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self._filter_combo)
        
        toolbar.addStretch()
        
        self._clear_btn = QPushButton("Limpar")
        self._clear_btn.clicked.connect(self.clear)
        toolbar.addWidget(self._clear_btn)
        
        layout.addLayout(toolbar)
        
        # Console
        self._console = QTextEdit()
        self._console.setReadOnly(True)
        self._console.setFont(QFont("Consolas", 10))
        self._console.setMinimumHeight(100)
        self._console.setStyleSheet("""
            QTextEdit {
                background-color: #14284c;
                color: #e5e7eb;
                border: 1px solid #1b3a69;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        layout.addWidget(self._console)
    
    @Slot(str, str, str)
    def add_event(
        self,
        message: str,
        level: str = "INFO",
        source: str = "",
    ) -> None:
        """
        Adiciona um evento ao console.
        
        Args:
            message: Mensagem do evento
            level: Nível (INFO, SUCCESS, WARNING, ERROR, DEBUG)
            source: Fonte do evento
        """
        try:
            event_level = EventLevel(level.upper())
        except ValueError:
            event_level = EventLevel.INFO
        
        entry = EventEntry(
            timestamp=datetime.now(),
            level=event_level,
            message=message,
            source=source,
        )
        
        self._events.append(entry)
        
        # Limita número de eventos
        if len(self._events) > self._max_events:
            self._events = self._events[-self._max_events:]
        
        # Adiciona ao console se passar pelo filtro
        if self._passes_filter(entry):
            self._append_entry(entry)
    
    def add_info(self, message: str, source: str = "") -> None:
        """Adiciona evento INFO."""
        self.add_event(message, "INFO", source)
    
    def add_success(self, message: str, source: str = "") -> None:
        """Adiciona evento SUCCESS."""
        self.add_event(message, "SUCCESS", source)
    
    def add_warning(self, message: str, source: str = "") -> None:
        """Adiciona evento WARNING."""
        self.add_event(message, "WARNING", source)
    
    def add_error(self, message: str, source: str = "") -> None:
        """Adiciona evento ERROR."""
        self.add_event(message, "ERROR", source)
    
    def clear(self) -> None:
        """Limpa o console."""
        self._events.clear()
        self._console.clear()
    
    def _append_entry(self, entry: EventEntry) -> None:
        """Adiciona entrada ao console."""
        self._console.append(entry.format_html())
        
        if self._auto_scroll:
            cursor = self._console.textCursor()
            cursor.movePosition(QTextCursor.End)
            self._console.setTextCursor(cursor)
    
    def _passes_filter(self, entry: EventEntry) -> bool:
        """Verifica se entrada passa pelo filtro."""
        if self._filter_level is None:
            return True
        return entry.level == self._filter_level
    
    def _on_filter_changed(self, index: int) -> None:
        """Handler para mudança de filtro."""
        self._filter_level = self._filter_combo.currentData()
        self._refresh()
    
    def _refresh(self) -> None:
        """Recarrega eventos com filtro atual."""
        self._console.clear()
        for entry in self._events:
            if self._passes_filter(entry):
                self._append_entry(entry)
