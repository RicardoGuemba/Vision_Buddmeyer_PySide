# -*- coding: utf-8 -*-
"""Fixtures compartilhadas para testes."""

import sys
from pathlib import Path

import pytest

# Garante que o pacote realtec_vision_buddmeyer está no path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def temp_config_dir(tmp_path):
    """Diretório temporário para arquivos de configuração."""
    return tmp_path


@pytest.fixture
def sample_config_yaml(temp_config_dir):
    """Arquivo YAML de configuração de exemplo válido."""
    config_path = temp_config_dir / "config.yaml"
    config_path.write_text("""
log_level: INFO
streaming:
  source_type: usb
  usb_camera_index: 0
  max_frame_buffer_size: 30
detection:
  default_model: PekingU/rtdetr_r50vd
  confidence_threshold: 0.5
  device: auto
output:
  rtsp_enabled: false
  http_port: 8080
  http_path: /stream
""", encoding="utf-8")
    return config_path


@pytest.fixture
def invalid_config_yaml(temp_config_dir):
    """Arquivo YAML com valores inválidos para testes de validação."""
    config_path = temp_config_dir / "invalid_config.yaml"
    config_path.write_text("""
streaming:
  source_type: invalid_type
detection:
  device: invalid_device
  confidence_threshold: 2.0
""", encoding="utf-8")
    return config_path
