"""Fumaça: todos os módulos do pacote importam (pega truncamentos e
dependências quebradas que a suíte funcional não exercita)."""

import importlib
import pkgutil

import carina


def test_every_module_imports():
    failed = []
    for info in pkgutil.walk_packages(carina.__path__, prefix="carina."):
        if info.name.endswith("__main__"):
            continue
        try:
            importlib.import_module(info.name)
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{info.name}: {exc}")
    assert not failed, "\n".join(failed)


def test_public_names_exist():
    from carina.render import dsoimages
    from carina.ui import skywidget, mainwindow

    assert hasattr(dsoimages, "DsoImageLayer")
    assert hasattr(skywidget, "SkyWidget")
    assert hasattr(mainwindow, "MainWindow")
