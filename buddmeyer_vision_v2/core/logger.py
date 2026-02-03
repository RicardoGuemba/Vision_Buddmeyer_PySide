# -*- coding: utf-8 -*-
"""
Sistema de logging estruturado usando structlog.
"""

import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from contextvars import ContextVar

import structlog
from structlog.stdlib import BoundLogger

# Context variable para correlation ID
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    """Retorna o correlation ID atual ou gera um novo."""
    cid = correlation_id_var.get()
    if not cid:
        cid = str(uuid.uuid4())[:8]
        correlation_id_var.set(cid)
    return cid


def set_correlation_id(cid: str) -> None:
    """Define o correlation ID."""
    correlation_id_var.set(cid)


def new_correlation_id() -> str:
    """Gera e define um novo correlation ID."""
    cid = str(uuid.uuid4())[:8]
    correlation_id_var.set(cid)
    return cid


def add_correlation_id(logger: logging.Logger, method_name: str, event_dict: dict) -> dict:
    """Adiciona correlation ID ao evento de log."""
    event_dict["correlation_id"] = get_correlation_id()
    return event_dict


def add_timestamp(logger: logging.Logger, method_name: str, event_dict: dict) -> dict:
    """Adiciona timestamp ISO 8601 ao evento de log (UTC)."""
    event_dict["timestamp"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return event_dict


def safe_value_processor(logger: logging.Logger, method_name: str, event_dict: dict) -> dict:
    """
    Processa valores que podem causar problemas de serialização.
    
    Converte objetos problemáticos para strings seguras para evitar
    recursão infinita durante logging.
    """
    for key, value in event_dict.items():
        if value is None or isinstance(value, (str, int, float, bool)):
            continue
        try:
            # Tenta converter para string de forma segura
            str(value)
        except (RecursionError, ValueError):
            # Se falhar, usa uma representação segura
            event_dict[key] = f"<{type(value).__name__} - serialization failed>"
    return event_dict


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    json_format: bool = False,
) -> None:
    """
    Configura o sistema de logging estruturado.
    
    Args:
        level: Nível de log (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Caminho para arquivo de log (opcional)
        json_format: Se True, usa formato JSON para console
    """
    # Configurar logging padrão
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # Handlers
    handlers = []
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    handlers.append(console_handler)
    
    # File handler (se especificado)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(log_level)
        handlers.append(file_handler)
    
    # Configurar logging básico
    logging.basicConfig(
        level=log_level,
        handlers=handlers,
        format="%(message)s",
    )
    
    # Processadores structlog
    shared_processors = [
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        add_correlation_id,
        add_timestamp,
        safe_value_processor,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]
    
    # Processador final (console)
    if json_format:
        console_processor = structlog.processors.JSONRenderer()
    else:
        console_processor = structlog.dev.ConsoleRenderer(
            colors=True,
            exception_formatter=structlog.dev.plain_traceback,
        )
    
    # Configurar structlog
    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Configurar formatter para handlers
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=console_processor,
        foreign_pre_chain=shared_processors,
    )
    
    for handler in handlers:
        handler.setFormatter(formatter)
    
    # JSON formatter para arquivo
    if log_file and len(handlers) > 1:
        json_formatter = structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(),
            foreign_pre_chain=shared_processors,
        )
        handlers[1].setFormatter(json_formatter)


def get_logger(name: str) -> BoundLogger:
    """
    Retorna um logger estruturado para o componente especificado.
    
    Args:
        name: Nome do componente (ex: "streaming.manager", "detection.engine")
    
    Returns:
        Logger estruturado
    """
    return structlog.get_logger(name)


# Loggers pré-configurados para componentes principais
class Loggers:
    """Container para loggers dos componentes principais."""
    
    @staticmethod
    def app() -> BoundLogger:
        return get_logger("app")
    
    @staticmethod
    def streaming() -> BoundLogger:
        return get_logger("streaming")
    
    @staticmethod
    def detection() -> BoundLogger:
        return get_logger("detection")
    
    @staticmethod
    def cip() -> BoundLogger:
        return get_logger("cip")
    
    @staticmethod
    def control() -> BoundLogger:
        return get_logger("control")
    
    @staticmethod
    def ui() -> BoundLogger:
        return get_logger("ui")
