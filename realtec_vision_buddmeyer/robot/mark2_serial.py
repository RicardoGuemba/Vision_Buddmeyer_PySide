# -*- coding: utf-8 -*-
"""Comunicação serial com o firmware Mark2 (Arduino Uno)."""

from __future__ import annotations

import threading
import time
from typing import Optional, Protocol

from core.logger import get_logger

logger = get_logger("robot.mark2_serial")


class SerialPortLike(Protocol):
    """Interface mínima compatível com serial.Serial (para mocks)."""

    def write(self, data: bytes) -> int: ...
    def readline(self) -> bytes: ...
    def close(self) -> None: ...
    @property
    def is_open(self) -> bool: ...


class Mark2SerialError(Exception):
    """Erro de protocolo ou transporte Mark2."""


class Mark2Serial:
    """
    Cliente serial único para o Mark2.

    Apenas o RobotWorker deve escrever nesta porta.
    """

    def __init__(
        self,
        port: str = "/dev/cu.usbmodem1101",
        baudrate: int = 115200,
        timeout_seconds: float = 5.0,
        serial_factory=None,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout_seconds = timeout_seconds
        self._serial_factory = serial_factory
        self._ser: Optional[SerialPortLike] = None
        self._lock = threading.RLock()
        self._last_response: str = ""
        self._angles = {"base": 90, "shoulder": 90, "elbow": 90, "gripper": 110}

    @property
    def is_connected(self) -> bool:
        return self._ser is not None and getattr(self._ser, "is_open", True)

    @property
    def last_response(self) -> str:
        return self._last_response

    @property
    def angles(self) -> dict:
        return dict(self._angles)

    def connect(self, wait_ready: bool = True) -> str:
        """Abre a porta e opcionalmente espera READY."""
        with self._lock:
            if self.is_connected:
                return self._last_response or "READY"

            if self._serial_factory is not None:
                self._ser = self._serial_factory(
                    self.port, self.baudrate, self.timeout_seconds
                )
            else:
                try:
                    import serial  # type: ignore
                except ImportError as exc:
                    raise Mark2SerialError(
                        "pyserial não instalado; pip install pyserial"
                    ) from exc
                self._ser = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    timeout=self.timeout_seconds,
                )
                # Arduino reset ao abrir USB
                time.sleep(2.0)

            if wait_ready:
                resp = self._read_line(deadline=time.monotonic() + self.timeout_seconds)
                if resp != "READY":
                    # alguns firmwares enviam lixo no reset; tenta mais uma linha
                    if resp and resp != "READY":
                        resp = self._read_line(
                            deadline=time.monotonic() + self.timeout_seconds
                        )
                    if resp != "READY":
                        self.disconnect()
                        raise Mark2SerialError(f"Esperado READY, recebido: {resp!r}")
                self._last_response = resp
                logger.info("mark2_serial_ready", port=self.port)
                return resp
            return ""

    def disconnect(self) -> None:
        with self._lock:
            if self._ser is not None:
                try:
                    self._ser.close()
                except Exception:
                    pass
                self._ser = None
            logger.info("mark2_serial_disconnected")

    def move(
        self,
        base: int,
        shoulder: int,
        elbow: int,
        gripper: int,
        speed: int = 15,
    ) -> str:
        cmd = f"MOVE,{int(base)},{int(shoulder)},{int(elbow)},{int(gripper)},{int(speed)}"
        resp = self._send_command(cmd)
        if resp == "OK":
            self._angles = {
                "base": int(base),
                "shoulder": int(shoulder),
                "elbow": int(elbow),
                "gripper": int(gripper),
            }
        return resp

    def home(self) -> str:
        resp = self._send_command("HOME")
        if resp == "OK":
            self._angles = {"base": 90, "shoulder": 90, "elbow": 90, "gripper": 110}
        return resp

    def stop(self) -> str:
        return self._send_command("STOP", accept=("STOPPED", "OK"))

    def _send_command(self, command: str, accept=("OK", "STOPPED")) -> str:
        with self._lock:
            if not self.is_connected or self._ser is None:
                raise Mark2SerialError("Serial não conectada")
            payload = (command.strip() + "\n").encode("ascii")
            logger.info("mark2_cmd", command=command)
            self._ser.write(payload)
            deadline = time.monotonic() + self.timeout_seconds
            resp = self._read_line(deadline=deadline)
            self._last_response = resp
            if resp.startswith("ERROR"):
                raise Mark2SerialError(resp)
            if resp not in accept and not resp.startswith("ERROR"):
                # READY residual após reset — ler próxima
                if resp == "READY":
                    resp = self._read_line(deadline=deadline)
                    self._last_response = resp
            if resp not in accept and not resp.startswith("ERROR"):
                raise Mark2SerialError(f"Timeout/resposta inesperada: {resp!r}")
            if resp.startswith("ERROR"):
                raise Mark2SerialError(resp)
            return resp

    def _read_line(self, deadline: float) -> str:
        if self._ser is None:
            return ""
        while time.monotonic() < deadline:
            raw = self._ser.readline()
            if not raw:
                continue
            line = raw.decode("ascii", errors="ignore").strip()
            if line:
                return line
        raise Mark2SerialError(
            f"Timeout à espera de resposta serial em {self.port}. "
            "Confirme: (1) porta do Arduino CH340 (/dev/cu.usbserial-*), "
            "não a webcam; (2) firmware mark2_uno.ino gravado a 115200 baud."
        )
