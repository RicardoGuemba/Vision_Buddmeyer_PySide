# -*- coding: utf-8 -*-
"""
Páginas (abas) da interface do sistema Buddmeyer Vision v2.0
"""

from .operation_page import OperationPage
from .configuration_page import ConfigurationPage
from .diagnostics_page import DiagnosticsPage
from .mark2_calibration_page import Mark2CalibrationPage

__all__ = [
    "OperationPage",
    "ConfigurationPage",
    "DiagnosticsPage",
    "Mark2CalibrationPage",
]
