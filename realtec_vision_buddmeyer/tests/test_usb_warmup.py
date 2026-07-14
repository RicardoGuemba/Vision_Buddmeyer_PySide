# -*- coding: utf-8 -*-
"""
Testes do warmup ativo do USBCameraAdapter.

Garantem que:
  1. O adaptador descarta frames pretos iniciais antes de retornar `open()`.
  2. O warmup tem timeout para não bloquear o startup do app indefinidamente
     se a câmera estiver permanentemente preta.
  3. `_create_frame_info` faz cópia defensiva do frame (buffer independente)
     para eliminar aliasing entre threads.

Não tocamos hardware: mocamos `cv2.VideoCapture` com um stub determinístico.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _FakeVideoCapture:
    """Stub determinístico de cv2.VideoCapture.

    Entrega `n_black` frames pretos e depois frames "vivos" (uint8 BGR com
    mean > 50, std > 20). Permite testar o warmup sem tocar hardware.
    """

    def __init__(self, n_black: int, return_none_on_failure: bool = False):
        self._n_black = n_black
        self._calls = 0
        self._opened = True
        self._return_none = return_none_on_failure
        self._props = {}

    def isOpened(self):
        return self._opened

    def set(self, prop_id, value):
        self._props[prop_id] = value
        return True

    def get(self, prop_id):
        if prop_id == 3:  # CAP_PROP_FRAME_WIDTH
            return self._props.get(3, 640)
        if prop_id == 4:  # CAP_PROP_FRAME_HEIGHT
            return self._props.get(4, 480)
        if prop_id == 5:  # CAP_PROP_FPS
            return 30.0
        if prop_id == 7:  # CAP_PROP_FRAME_COUNT
            return 0
        return 0

    def read(self):
        self._calls += 1
        if self._calls <= self._n_black:
            if self._return_none:
                return False, None
            # Frame "preto": mean=0, std=0 (pior caso)
            return True, np.zeros((480, 640, 3), dtype=np.uint8)
        # Frame "vivo" — gradiente determinístico para garantir mean/std altos
        rng = np.random.default_rng(self._calls)
        return True, rng.integers(40, 220, size=(480, 640, 3), dtype=np.uint8)

    def release(self):
        self._opened = False


@pytest.fixture
def patched_cv2():
    """Substitui cv2.VideoCapture pelo stub durante o teste."""
    import streaming.source_adapters as sa

    original = sa.cv2.VideoCapture
    yield sa
    sa.cv2.VideoCapture = original


def test_warmup_drains_black_frames_before_returning_ready(patched_cv2):
    """O adaptador deve descartar 4 frames pretos e só então sinalizar 'pronto'."""
    sa = patched_cv2

    fake = _FakeVideoCapture(n_black=4)
    sa.cv2.VideoCapture = MagicMock(return_value=fake)

    adapter = sa.USBCameraAdapter(camera_index=0, width=640, height=480)
    with patch.object(sa, "logger") as log_mock:
        ok = adapter.open()
        assert ok is True
        # Após open(), o warmup já deve ter sido emitido com sucesso
        events = [c.args[0] for c in log_mock.info.call_args_list]
        assert "usb_camera_warmup_ok" in events, (
            f"Esperava o evento usb_camera_warmup_ok; vi {events}"
        )
        # Frames consumidos no warmup: 4 pretos + pelo menos 2 não-pretos
        assert fake._calls >= 6


def test_warmup_does_not_block_indefinitely_if_camera_stays_black(patched_cv2):
    """
    Se a câmera entrega só frames pretos, o warmup deve terminar dentro do
    orçamento e logar warning — em vez de travar o startup do app.
    """
    sa = patched_cv2

    # Mais frames pretos do que o adapter aceita; deve estourar timeout/limite
    fake = _FakeVideoCapture(n_black=10_000)
    sa.cv2.VideoCapture = MagicMock(return_value=fake)

    adapter = sa.USBCameraAdapter(camera_index=0)
    with patch.object(sa, "logger") as log_mock:
        ok = adapter.open()
        # open() não levanta — apenas loga warning para não travar a app
        assert ok is True
        warning_events = [c.args[0] for c in log_mock.warning.call_args_list]
        assert "usb_camera_warmup_timeout" in warning_events, (
            f"Esperava warning de timeout; vi {warning_events}"
        )
        # Warmup limitado: não deve consumir milhares de frames mesmo
        # se a câmera prometer entregar pretos para sempre.
        assert fake._calls <= 200


def test_warmup_handles_read_failures_gracefully(patched_cv2):
    """Reads que retornam (False, None) durante o warmup não devem quebrar."""
    sa = patched_cv2

    fake = _FakeVideoCapture(n_black=2, return_none_on_failure=True)
    sa.cv2.VideoCapture = MagicMock(return_value=fake)

    adapter = sa.USBCameraAdapter(camera_index=0)
    # Ainda que os 2 primeiros reads falhem, o warmup deve sair OK
    # nos frames seguintes (ret=True com conteúdo "vivo").
    with patch.object(sa, "logger"):
        ok = adapter.open()
        assert ok is True


def test_create_frame_info_makes_independent_buffer():
    """
    `_create_frame_info` deve produzir um FrameInfo cujo `.frame` aponta
    para um buffer INDEPENDENTE do array de entrada — para que mutations
    a jusante (overlay, encoding, etc.) não corrompam frames já entregues
    a outras threads.
    """
    import streaming.source_adapters as sa

    adapter = sa.USBCameraAdapter(camera_index=0)
    rng = np.random.default_rng(0)
    original = rng.integers(0, 256, size=(120, 160, 3), dtype=np.uint8)
    snapshot = original.copy()

    info = adapter._create_frame_info(original)
    # Mutamos o buffer original — o frame guardado em `info` NÃO pode mudar
    original[:, :, :] = 0
    assert np.array_equal(info.frame, snapshot), (
        "FrameInfo.frame deve ser uma cópia, não um view do array original"
    )


def test_create_frame_info_handles_non_contiguous_array():
    """
    Frames originados de slices/views (ex.: cv2 com algumas pipelines) podem
    ser não-contíguos. `_create_frame_info` deve normalizar para contíguo
    para evitar surpresas em `Image.fromarray` ou serialização downstream.
    """
    import streaming.source_adapters as sa

    adapter = sa.USBCameraAdapter(camera_index=0)
    rng = np.random.default_rng(1)
    big = rng.integers(0, 256, size=(120, 160, 3), dtype=np.uint8)
    # View não-contíguo (canais reversos cria stride negativo)
    view = big[:, :, ::-1]
    assert not view.flags["C_CONTIGUOUS"]

    info = adapter._create_frame_info(view)
    assert info.frame.flags["C_CONTIGUOUS"], (
        "FrameInfo.frame deve ser contíguo para uso seguro downstream"
    )
