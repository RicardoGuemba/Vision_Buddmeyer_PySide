# -*- coding: utf-8 -*-
"""
Logger específico para comunicação CIP.
"""

from datetime import datetime
from typing import Any, Optional
from dataclasses import dataclass, field
from collections import deque
from threading import Lock

from core.logger import get_logger

logger = get_logger("cip")


@dataclass
class CIPLogEntry:
    """Entrada de log CIP."""
    
    timestamp: datetime
    operation: str  # read, write, connect, disconnect
    tag_name: Optional[str]
    value: Optional[Any]
    success: bool
    error: Optional[str] = None
    duration_ms: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "operation": self.operation,
            "tag_name": self.tag_name,
            "value": self.value,
            "success": self.success,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


class CIPLogger:
    """
    Logger para operações CIP.
    
    Mantém histórico de operações e estatísticas.
    """
    
    def __init__(self, max_entries: int = 1000):
        self._entries: deque = deque(maxlen=max_entries)
        self._lock = Lock()
        self._stats = {
            "total_reads": 0,
            "total_writes": 0,
            "read_errors": 0,
            "write_errors": 0,
            "connections": 0,
            "disconnections": 0,
        }
    
    def log_read(
        self,
        tag_name: str,
        value: Any,
        success: bool,
        error: Optional[str] = None,
        duration_ms: float = 0.0,
    ) -> None:
        """Registra uma operação de leitura."""
        # Sanitiza erro para evitar problemas de serialização
        safe_error = self._sanitize_error(error) if error else None
        
        entry = CIPLogEntry(
            timestamp=datetime.now(),
            operation="read",
            tag_name=tag_name,
            value=value if success else None,
            success=success,
            error=safe_error,
            duration_ms=duration_ms,
        )
        
        with self._lock:
            self._entries.append(entry)
            self._stats["total_reads"] += 1
            if not success:
                self._stats["read_errors"] += 1
        
        if success:
            logger.debug("cip_read", tag=tag_name, value=value, duration_ms=duration_ms)
        else:
            logger.warning("cip_read_error", tag=tag_name, error=safe_error)
    
    def log_write(
        self,
        tag_name: str,
        value: Any,
        success: bool,
        error: Optional[str] = None,
        duration_ms: float = 0.0,
    ) -> None:
        """Registra uma operação de escrita."""
        # Sanitiza erro para evitar problemas de serialização
        safe_error = self._sanitize_error(error) if error else None
        
        entry = CIPLogEntry(
            timestamp=datetime.now(),
            operation="write",
            tag_name=tag_name,
            value=value,
            success=success,
            error=safe_error,
            duration_ms=duration_ms,
        )
        
        with self._lock:
            self._entries.append(entry)
            self._stats["total_writes"] += 1
            if not success:
                self._stats["write_errors"] += 1
        
        if success:
            logger.debug("cip_write", tag=tag_name, value=value, duration_ms=duration_ms)
        else:
            logger.warning("cip_write_error", tag=tag_name, value=value, error=safe_error)
    
    def log_connect(self, ip: str, success: bool, error: Optional[str] = None) -> None:
        """Registra tentativa de conexão."""
        # Sanitiza erro para evitar problemas de serialização
        safe_error = self._sanitize_error(error) if error else None
        
        entry = CIPLogEntry(
            timestamp=datetime.now(),
            operation="connect",
            tag_name=None,
            value=ip,
            success=success,
            error=safe_error,
        )
        
        with self._lock:
            self._entries.append(entry)
            self._stats["connections"] += 1
        
        if success:
            logger.info("cip_connected", ip=ip)
        else:
            logger.error("cip_connect_error", ip=ip, error=safe_error)
    
    def log_disconnect(self, reason: str = "normal") -> None:
        """Registra desconexão."""
        entry = CIPLogEntry(
            timestamp=datetime.now(),
            operation="disconnect",
            tag_name=None,
            value=reason,
            success=True,
        )
        
        with self._lock:
            self._entries.append(entry)
            self._stats["disconnections"] += 1
        
        logger.info("cip_disconnected", reason=reason)
    
    def get_recent_entries(self, count: int = 100) -> list:
        """Retorna entradas recentes."""
        with self._lock:
            return [e.to_dict() for e in list(self._entries)[-count:]]
    
    def get_stats(self) -> dict:
        """Retorna estatísticas."""
        with self._lock:
            return self._stats.copy()
    
    def get_error_rate(self) -> float:
        """Calcula taxa de erro."""
        with self._lock:
            total = self._stats["total_reads"] + self._stats["total_writes"]
            errors = self._stats["read_errors"] + self._stats["write_errors"]
            return errors / total if total > 0 else 0.0
    
    def clear(self) -> None:
        """Limpa histórico."""
        with self._lock:
            self._entries.clear()
    
    @staticmethod
    def _sanitize_error(error: Optional[str]) -> Optional[str]:
        """
        Sanitiza mensagem de erro para evitar recursão durante serialização.
        
        Remove detalhes complexos que podem causar problemas com structlog.
        """
        if error is None:
            return None
        
        try:
            # Se for string, apenas trunca se muito longa
            error_str = str(error)
            if len(error_str) > 500:
                return error_str[:500] + "..."
            return error_str
        except Exception as e:
            # Se houver erro ao converter para string, retorna um genérico
            return f"Error serialization failed: {type(error).__name__}"
