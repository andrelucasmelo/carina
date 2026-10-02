"""Configuração comum dos testes.

Alguns testes desenham com QPainter (as cartas de localização do PDF) e
por isso precisam de uma aplicação Qt viva. Criamos uma única, em modo
**offscreen**: nada aparece na tela, nenhum foco é roubado e a suíte
continua rodando em máquinas sem servidor gráfico.
"""

import os
import tempfile

import pytest
from PySide6.QtCore import QSettings

# Nenhum teste lê ou grava as preferências REAIS do usuário (registro do
# Windows): o QSettings passa a usar um .ini descartável. Precisa acontecer
# antes de qualquer QSettings ser criado — por isso no nível do módulo.
_SETTINGS_DIR = tempfile.mkdtemp(prefix="carina-test-settings-")
QSettings.setDefaultFormat(QSettings.IniFormat)
QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, _SETTINGS_DIR)


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    """Aplicação Qt offscreen compartilhada por toda a sessão de testes.

    É uma ``QApplication`` (de QtWidgets), não uma ``QGuiApplication``:
    alguns testes instanciam widgets — como o canvas do rastreamento — e
    criar um QWidget sem QApplication derruba o processo.
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture(scope="session", autouse=True)
def isolated_userdata(tmp_path_factory):
    """Nenhum teste lê ou grava o carina.sqlite real do usuário."""
    from carina.core import userdata

    data = userdata.UserData(tmp_path_factory.mktemp("userdata") / "carina.sqlite")
    userdata.set_instance(data)
    yield data
    data.close()
    userdata.set_instance(None)
