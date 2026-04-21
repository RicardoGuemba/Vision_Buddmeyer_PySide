# -*- coding: utf-8 -*-
"""Testes unitários para config/settings."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from config.settings import (
    Settings,
    StreamingSettings,
    DetectionSettings,
    CIPSettings,
    OutputSettings,
    get_settings,
    DEFAULT_ROI_QUARTER_AREA,
)


class TestStreamingSettings:
    """Testes de StreamingSettings."""

    def test_source_type_valid(self):
        """source_type aceita valores válidos."""
        for t in ("video", "usb", "rtsp", "gige", "gentl"):
            s = StreamingSettings(source_type=t)
            assert s.source_type == t

    def test_source_type_invalid(self):
        """source_type rejeita valores inválidos."""
        with pytest.raises(ValidationError):
            StreamingSettings(source_type="invalid_type")

    def test_defaults(self):
        """Valores padrão são corretos."""
        s = StreamingSettings()
        assert s.source_type == "usb"
        assert s.usb_camera_index == 0
        assert s.max_frame_buffer_size == 30


class TestDetectionSettings:
    """Testes de DetectionSettings."""

    def test_device_valid(self):
        """device aceita cpu, cuda, mps, auto."""
        for d in ("cpu", "cuda", "mps", "auto"):
            s = DetectionSettings(device=d)
            assert s.device == d

    def test_device_invalid(self):
        """device rejeita valores inválidos."""
        with pytest.raises(ValidationError):
            DetectionSettings(device="invalid_device")

    def test_confidence_range(self):
        """confidence_threshold deve estar em [0, 1]."""
        with pytest.raises(ValidationError):
            DetectionSettings(confidence_threshold=2.0)
        with pytest.raises(ValidationError):
            DetectionSettings(confidence_threshold=-0.1)


class TestSettingsFromYaml:
    """Testes de Settings.from_yaml."""

    def test_from_yaml_valid(self, sample_config_yaml):
        """Carrega YAML válido corretamente."""
        s = Settings.from_yaml(sample_config_yaml)
        assert s.streaming.source_type == "usb"
        assert s.streaming.usb_camera_index == 0
        assert s.detection.default_model == "PekingU/rtdetr_r50vd"
        assert s.cip.ip == "192.168.1.10"
        assert s.cip.simulated is True

    def test_from_yaml_nonexistent(self, temp_config_dir):
        """Arquivo inexistente retorna Settings com defaults."""
        path = temp_config_dir / "nonexistent.yaml"
        s = Settings.from_yaml(path)
        assert isinstance(s, Settings)
        assert s.streaming.source_type == "usb"

    def test_from_yaml_invalid_values_raises(self, invalid_config_yaml):
        """YAML com valores inválidos levanta ValidationError."""
        with pytest.raises(ValidationError):
            Settings.from_yaml(invalid_config_yaml)


class TestSettingsToYaml:
    """Testes de Settings.to_yaml."""

    def test_to_yaml_roundtrip(self, sample_config_yaml, temp_config_dir):
        """Salvar e recarregar preserva dados."""
        s1 = Settings.from_yaml(sample_config_yaml)
        out_path = temp_config_dir / "out_config.yaml"
        s1.to_yaml(out_path)
        assert out_path.exists()
        s2 = Settings.from_yaml(out_path)
        assert s2.streaming.source_type == s1.streaming.source_type
        assert s2.detection.confidence_threshold == s1.detection.confidence_threshold

    def test_to_yaml_creates_dir(self, temp_config_dir):
        """to_yaml cria diretório pai se não existir."""
        out_path = temp_config_dir / "subdir" / "config.yaml"
        s = Settings()
        s.to_yaml(out_path)
        assert out_path.exists()


class TestGetSettings:
    """Testes de get_settings."""

    def test_get_settings_returns_instance(self, sample_config_yaml):
        """get_settings retorna instância de Settings."""
        s = get_settings(sample_config_yaml, reload=True)
        assert isinstance(s, Settings)

    def test_get_settings_reload(self, sample_config_yaml, temp_config_dir):
        """reload=True força recarregar do arquivo."""
        s1 = get_settings(sample_config_yaml, reload=True)
        # Modifica arquivo
        new_path = temp_config_dir / "config2.yaml"
        new_path.write_text("""
streaming:
  source_type: rtsp
  rtsp_url: rtsp://test
""", encoding="utf-8")
        s2 = get_settings(new_path, reload=True)
        assert s2.streaming.source_type == "rtsp"
        assert s2.streaming.rtsp_url == "rtsp://test"


class TestOutputSettings:
    """Testes de OutputSettings (stream HTTP MJPEG)."""

    def test_output_defaults(self):
        """OutputSettings tem http_port e http_path por padrão."""
        o = OutputSettings()
        assert o.http_port == 8080
        assert o.http_path == "/stream"
        assert o.rtsp_enabled is False

    def test_output_from_yaml(self, sample_config_yaml):
        """OutputSettings carrega http_port e http_path do YAML."""
        s = Settings.from_yaml(sample_config_yaml)
        assert s.output.http_port == 8080
        assert s.output.http_path == "/stream"


class TestDefaultRoi:
    """Testes de DEFAULT_ROI_QUARTER_AREA."""

    def test_default_roi_quarter_area(self):
        """ROI padrão é 25% da área (ex.: 640x480 -> 277x277 centralizado)."""
        assert len(DEFAULT_ROI_QUARTER_AREA) == 4
        x, y, w, h = DEFAULT_ROI_QUARTER_AREA
        assert w == 277 and h == 277  # 25% de 640x480
        assert x == 181 and y == 101  # centralizado


class TestSettingsPaths:
    """Testes de métodos de path."""

    def test_get_base_path(self):
        """get_base_path retorna Path do diretório do pacote."""
        s = Settings()
        base = s.get_base_path()
        assert isinstance(base, Path)
        assert base.exists()
        assert "realtec_vision_buddmeyer" in str(base)

    def test_get_models_path_relative(self):
        """get_models_path resolve caminho relativo."""
        s = Settings()
        s.detection.model_path = "model_best"
        p = s.get_models_path()
        assert isinstance(p, Path)
        assert "model_best" in str(p)
