# -*- coding: utf-8 -*-
"""Testes de shutdown estável do sistema."""

import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


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
        from detection.events import DetectionEvent
        from ui.pages.operation_page import OperationPage

        page = OperationPage()
        qtbot.addWidget(page)
        page._is_running = False

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
        """MainWindow inicia shutdown unificado ao fechar sem sistema rodando."""
        from ui.main_window import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        qtbot.waitExposed(window)
        window.close()
        assert window._exit_in_progress
        qtbot.wait(250)
        window._complete_exit()
        assert window.isHidden() or not window.isVisible()

    def test_shutdown_cancels_model_loading(self, qtbot):
        """shutdown() limpa estado de carregamento do modelo sem QThread pendente."""
        from ui.pages.operation_page import OperationPage

        page = OperationPage()
        qtbot.addWidget(page)
        page._model_loading = True
        page._pending_start_source_label = "USB"
        page.shutdown()
        assert not page._model_loading
        assert page._pending_start_source_label is None

    def test_shutdown_stops_mark2_worker(self, qtbot):
        """shutdown() para o Mark2 sem erro."""
        from ui.pages.operation_page import OperationPage

        page = OperationPage()
        qtbot.addWidget(page)
        page.shutdown()
        assert not page._is_running

    def test_main_window_begin_exit_idempotent(self, qtbot):
        """_begin_exit pode ser chamado uma vez sem erro."""
        from ui.main_window import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        qtbot.waitExposed(window)
        window._begin_exit()
        assert window._exit_in_progress
        window._begin_exit()
        assert window._exit_in_progress

    def test_is_busy_for_exit_model_loading(self, qtbot):
        """Carregamento de modelo exige confirmação de saída."""
        from ui.main_window import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)
        window._operation_page._model_loading = True
        assert window._is_busy_for_exit()

    def test_diagnostics_stop_timers(self, qtbot):
        """DiagnosticsPage para timer de atualização."""
        from ui.pages.diagnostics_page import DiagnosticsPage

        page = DiagnosticsPage()
        qtbot.addWidget(page)
        assert page._update_timer.isActive()
        page.stop_timers()
        assert not page._update_timer.isActive()

    def test_model_load_skipped_after_shutdown(self, qtbot):
        """Carregamento do modelo não continua após shutdown."""
        from ui.pages.operation_page import OperationPage

        page = OperationPage()
        qtbot.addWidget(page)
        page._model_loading = True
        page.shutdown()
        page._run_model_load_on_main_thread()
        assert not page._model_loading

