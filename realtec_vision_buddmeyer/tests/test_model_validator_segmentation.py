# -*- coding: utf-8 -*-
"""Testes do ModelValidator para modelos de instance segmentation."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _make_model_dir(tmp_path: Path, model_type: str, extra: dict | None = None) -> Path:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    config = {"model_type": model_type, "num_labels": 1}
    if extra:
        config.update(extra)
    (model_dir / "config.json").write_text(json.dumps(config), encoding="utf-8")
    (model_dir / "preprocessor_config.json").write_text("{}", encoding="utf-8")
    (model_dir / "model.safetensors").write_bytes(b"\x00")
    return model_dir


class TestModelValidatorSegmentation:
    def test_mask2former_is_valid(self, tmp_path):
        from detection.model_validator import ModelValidator

        model_dir = _make_model_dir(tmp_path, "mask2former")
        ok, missing, warnings_list = ModelValidator.validate_model_directory(model_dir)
        assert ok is True, f"missing={missing}"

    def test_detr_still_valid(self, tmp_path):
        from detection.model_validator import ModelValidator

        model_dir = _make_model_dir(tmp_path, "detr")
        ok, missing, _ = ModelValidator.validate_model_directory(model_dir)
        assert ok is True, f"missing={missing}"

    def test_rtdetr_variants_valid(self, tmp_path):
        from detection.model_validator import ModelValidator

        for mt in ("rt_detr", "rtdetr"):
            sub = tmp_path / mt
            sub.mkdir()
            (sub / "config.json").write_text(
                json.dumps({"model_type": mt, "num_labels": 1}), encoding="utf-8"
            )
            (sub / "preprocessor_config.json").write_text("{}", encoding="utf-8")
            (sub / "model.safetensors").write_bytes(b"\x00")
            ok, missing, _ = ModelValidator.validate_model_directory(sub)
            assert ok is True, f"{mt}: missing={missing}"

    def test_unknown_model_type_rejected(self, tmp_path):
        from detection.model_validator import ModelValidator

        model_dir = _make_model_dir(tmp_path, "some_unknown_model_type")
        ok, missing, _ = ModelValidator.validate_model_directory(model_dir)
        assert ok is False
        assert any("some_unknown_model_type" in m or "config.json" in m for m in missing)

    def test_check_model_ready_message(self, tmp_path):
        from detection.model_validator import ModelValidator

        model_dir = _make_model_dir(tmp_path, "mask2former")
        ready, msg = ModelValidator.check_model_ready(model_dir)
        assert ready is True
        assert "válido" in msg.lower() or "pronto" in msg.lower()
