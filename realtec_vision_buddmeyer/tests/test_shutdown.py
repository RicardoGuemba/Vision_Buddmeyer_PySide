# -*- coding: utf-8 -*-
"""Testes de shutdown estável do sistema."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _install_fake_stream(page):
    """Substitui start/stop/change_source do StreamManager por mocks (sem hardware)."""
    sm = page._stream_manager
    counts = {"start": 0, "stop": 0}

    def fake_start():
        counts["start"] += 1
        sm._is_running = True
        return True

    def fake_stop():
        counts["stop"] += 1
        sm._is_running = False

    def fake_change_source(**kwargs):
        return True

    sm.start = fake_start
    sm.stop = fake_stop
    sm.change_source = fake_change_source
    sm._is_running = False
    return sm, counts


def _mark_model_loaded(page):
    page._inference_engine._loader._model = object()
    page._inference_engine._loader._processor = object()
    page._inference_engine.start = lambda: True
    page._inference_engine.stop = lambda: None


class TestShutdownStability:
    """Testes de estabilidade ao parar e sair."""

    def test_stop_system_idempotent(self, qtbot):
        """Chamar _stop_system duas vezes não causa erro."""
        from ui.pages.operation_page import OperationPage

        page = OperationPage()
        qtbot.addWidget(page)
        page._stop_system()
        page._stop_system()
        assert not page._is_running

    def test_stop_system_when_not_running(self, qtbot):
        """_stop_system quando não está rodando retorna imediatamente."""
        from ui.pages.operation_page import OperationPage

        page = OperationPage()
        qtbot.addWidget(page)
        assert not page._is_running
        page._stop_system()
        assert not page._is_running

    def test_handlers_ignore_when_not_running(self, qtbot):
        """Handlers retornam cedo quando _is_running é False."""
        from datetime import datetime

        from detection.events import DetectionEvent
        from ui.pages.operation_page import OperationPage

        page = OperationPage()
        qtbot.addWidget(page)
        page._is_running = False

        page._on_cycle_summary([])
        page._on_cycle_summary([{"step": "x", "timestamp": datetime.now()}])
        page._on_cycle_step("test")

        evt = DetectionEvent(
            detected=True,
            class_name="test",
            confidence=0.9,
            centroid=(0.0, 0.0),
            detection_count=1,
        )
        page._on_detection(evt)

        assert not page._is_running

    def test_main_window_close_without_running(self, qtbot):
        """MainWindow fecha sem erro quando sistema não está rodando."""
        from ui.main_window import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        qtbot.waitExposed(window)
        window.close()
        assert window.isHidden() or not window.isVisible()

    def test_stop_releases_stream_while_model_still_loading(self, qtbot):
        """
        Causa raiz: após Iniciar, a câmera sobe antes do modelo e _is_running
        fica False. Parar/fechar nesse intervalo deve mesmo assim liberar o stream.
        """
        from ui.pages.operation_page import OperationPage

        page = OperationPage()
        qtbot.addWidget(page)
        sm, counts = _install_fake_stream(page)

        sm.start()
        page._is_running = False
        page._pending_start_source_label = "Câmera USB"
        page._model_loader_thread = MagicMock()
        page._model_loader_thread.isRunning.return_value = True

        page._stop_system()

        assert counts["stop"] == 1
        assert not sm.is_running
        assert page._pending_start_source_label is None
        assert page._model_load_cancelled is True

    def test_start_stop_start_cycle_with_mocks(self, qtbot, monkeypatch):
        """Ciclo iniciar → encerrar → iniciar novamente sem câmera/CLP físicos."""
        import asyncio

        from ui.pages.operation_page import OperationPage

        page = OperationPage()
        qtbot.addWidget(page)
        sm, counts = _install_fake_stream(page)
        _mark_model_loaded(page)
        page._robot_controller.start = lambda: None
        page._robot_controller.stop = lambda: None

        def _drop_coro(coro):
            coro.close()
            return MagicMock()

        monkeypatch.setattr(asyncio, "create_task", _drop_coro)

        page._source_combo.setCurrentIndex(1)  # USB, sem arquivo CTI/vídeo

        page._start_system()
        assert counts["start"] == 1
        assert page._is_running
        assert sm.is_running

        page._stop_system()
        assert counts["stop"] >= 1
        assert not page._is_running
        assert not sm.is_running

        page._start_system()
        assert counts["start"] == 2
        assert page._is_running
        assert sm.is_running

        page._stop_system()
        assert not page._is_running
        assert not sm.is_running


class TestStreamManagerRestart:
    """Start/stop/start do StreamManager com adaptador mock (sem hardware)."""

    def test_start_stop_start_closes_adapter_each_cycle(self, qtbot, monkeypatch):
        from streaming.frame_buffer import FrameInfo
        from streaming import stream_manager as sm_mod
        from streaming.stream_manager import StreamManager

        class FakeAdapter:
            def __init__(self):
                self.source_type = type("T", (), {"value": "usb"})()
                self.open_count = 0
                self.close_count = 0
                self._is_open = False
                self._stop_requested = False

            @property
            def is_open(self):
                return self._is_open

            def open(self):
                self.open_count += 1
                self._stop_requested = False
                self._is_open = True
                return True

            def request_stop(self):
                self._stop_requested = True

            def read(self):
                if self._stop_requested or not self._is_open:
                    return None
                frame = np.zeros((4, 4, 3), dtype=np.uint8)
                return FrameInfo.from_frame(frame, 1, "usb")

            def close(self):
                self.close_count += 1
                self._is_open = False

            def get_properties(self):
                return {"fps": 30.0}

        adapters = []

        def fake_create_adapter(**kwargs):
            adapter = FakeAdapter()
            adapters.append(adapter)
            return adapter

        if StreamManager._instance is not None:
            try:
                StreamManager._instance.stop()
            except Exception:
                pass
            StreamManager._instance = None

        monkeypatch.setattr(sm_mod, "create_adapter", fake_create_adapter)
        mgr = StreamManager()
        mgr.change_source(source_type="usb", camera_index=0)

        assert mgr.start()
        qtbot.waitUntil(lambda: adapters and adapters[0].open_count >= 1, timeout=3000)
        mgr.stop()
        qtbot.waitUntil(lambda: adapters[0].close_count >= 1, timeout=3000)
        assert not adapters[0].is_open
        assert not mgr.is_running

        assert mgr.start()
        qtbot.waitUntil(lambda: len(adapters) >= 2 and adapters[1].open_count >= 1, timeout=3000)
        mgr.stop()
        qtbot.waitUntil(lambda: adapters[1].close_count >= 1, timeout=3000)
        assert not adapters[1].is_open
        assert not mgr.is_running

    def test_stop_closes_partial_start(self, qtbot):
        """stop() libera adaptador mesmo se _is_running ficou False (start a meio)."""
        from streaming.stream_manager import StreamManager

        class PartialAdapter:
            def __init__(self):
                self._is_open = True
                self.closed = False

            @property
            def is_open(self):
                return self._is_open

            def request_stop(self):
                pass

            def close(self):
                self.closed = True
                self._is_open = False

        if StreamManager._instance is not None:
            try:
                StreamManager._instance.stop()
            except Exception:
                pass

        mgr = StreamManager()
        adapter = PartialAdapter()
        mgr._adapter = adapter
        mgr._worker = None
        mgr._is_running = False

        mgr.stop()

        assert adapter.closed
        assert mgr._adapter is None
        assert not mgr.is_running

