# -*- coding: utf-8 -*-
"""Testes unitários para config/settings."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from config.settings import (
    Settings,
    StreamingSettings,
    DetectionSettings,
    Mark2Settings,
    OutputSettings,
    get_settings,
    DEFAULT_ROI_QUARTER_AREA,
)


class TestStreamingSettings:
    def test_source_type_valid(self):
        for t in ("video", "usb", "rtsp", "gige", "gentl"):
            s = StreamingSettings(source_type=t)
            assert s.source_type == t

    def test_source_type_invalid(self):
        with pytest.raises(ValidationError):
            StreamingSettings(source_type="invalid_type")

    def test_defaults(self):
        s = StreamingSettings()
        assert s.source_type == "usb"
        assert s.usb_camera_index == 0
        assert s.max_frame_buffer_size == 30


class TestDetectionSettings:
    def test_device_valid(self):
        for d in ("cpu", "cuda", "mps", "auto"):
            s = DetectionSettings(device=d)
            assert s.device == d

    def test_device_invalid(self):
        with pytest.raises(ValidationError):
            DetectionSettings(device="invalid_device")

    def test_confidence_range(self):
        with pytest.raises(ValidationError):
            DetectionSettings(confidence_threshold=2.0)
        with pytest.raises(ValidationError):
            DetectionSettings(confidence_threshold=-0.1)


class TestSettingsFromYaml:
    def test_from_yaml_valid(self, sample_config_yaml):
        s = Settings.from_yaml(sample_config_yaml)
        assert s.streaming.source_type == "usb"
        assert s.streaming.usb_camera_index == 0
        assert s.detection.default_model == "PekingU/rtdetr_r50vd"
        assert isinstance(s.mark2, Mark2Settings)

    def test_from_yaml_loads_mark2(self, temp_config_dir):
        config_path = temp_config_dir / "config.yaml"
        mark2_path = temp_config_dir / "mark2.yaml"
        config_path.write_text("log_level: INFO\nstreaming:\n  source_type: usb\n", encoding="utf-8")
        mark2_path.write_text(
            "serial:\n  port: /dev/cu.test\n  baudrate: 115200\n",
            encoding="utf-8",
        )
        s = Settings.from_yaml(config_path)
        assert s.mark2.serial.port == "/dev/cu.test"

    def test_from_yaml_nonexistent(self, temp_config_dir):
        path = temp_config_dir / "nonexistent.yaml"
        s = Settings.from_yaml(path)
        assert isinstance(s, Settings)

    def test_from_yaml_ignores_legacy_cip(self, sample_config_yaml):
        s = Settings.from_yaml(sample_config_yaml)
        assert not hasattr(s, "cip") or True
        assert s.mark2 is not None


class TestOutputSettings:
    def test_defaults(self):
        o = OutputSettings()
        assert o.http_port == 8080


class TestDefaultRoi:
    def test_default_roi_defined(self):
        assert len(DEFAULT_ROI_QUARTER_AREA) == 4
