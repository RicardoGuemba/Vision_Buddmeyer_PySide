#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke serial Mark2 — skip se porta ausente.

Uso:
  MARK2_PORT=/dev/cu.usbmodem1101 python -m scripts.smoke_test_mark2_serial
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    port = os.environ.get("MARK2_PORT", "")
    if not port:
        from config import get_settings
        port = get_settings().mark2.serial.port
    if not Path(port).exists() and not port.startswith("/dev/"):
        print(f"SKIP: porta {port} não encontrada (defina MARK2_PORT)")
        return 0
    # Em macOS /dev/cu.* pode não existir no Path.exists de forma fiável
    try:
        from robot.mark2_serial import Mark2Serial
        ser = Mark2Serial(port=port)
        print(f"A ligar {port}...")
        print(ser.connect())
        print(ser.home())
        print("OK smoke serial")
        ser.disconnect()
        return 0
    except Exception as exc:
        print(f"FALHA / SKIP hardware: {exc}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
