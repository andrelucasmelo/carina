"""Configuração comum dos testes.

Alguns testes desenham com QPainter (as cartas de localização do PDF) e
por isso precisam de uma aplicação Qt viva. Criamos uma única, em modo
**offscreen**: nada aparece na tela, nenhum foco é roubado e a suíte
continua rodando em máquinas sem servidor gráfico.
"""

import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    """Aplicação Qt offscreen compartilhada por toda a sessão de testes."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance()
    if app is None:
        app = QGuiApplication([])
    yield app
