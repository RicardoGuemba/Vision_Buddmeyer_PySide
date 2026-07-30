# -*- coding: utf-8 -*-
"""Teste leve do layout da barra de controlos da Operação."""

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_operation_mark2_buttons_have_readable_labels(qtbot):
    from ui.pages.operation_page import OperationPage

    page = OperationPage()
    qtbot.addWidget(page)
    page.show()
    qtbot.waitExposed(page)

    assert page._mark2_connect_btn.text() == "Conectar"
    assert page._mark2_open_gripper_btn.text() == "Abrir garra"
    assert page._mark2_close_gripper_btn.text() == "Fechar garra"
    assert page._mark2_stop_btn.text() == "STOP"
    assert "movimento" in page._smoke_cb.text().lower() or "motor" in page._smoke_cb.text().lower()
    # botões com largura mínima para não truncar
    assert page._mark2_connect_btn.minimumWidth() >= 110
    assert page._play_btn.text() == "▶ Iniciar"
