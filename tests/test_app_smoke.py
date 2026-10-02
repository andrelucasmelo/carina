"""Fumaça de ponta a ponta: o aplicativo abre, renderiza e grava um PNG.

Roda o Carina num subprocesso com a opção ``--screenshot`` (a mesma das
validações visuais). Pega o que a importação não pega: janela que não
monta, menus quebrados, estado salvo corrompido. Define
``CARINA_SKIP_GUI=1`` para pular em máquinas sem OpenGL.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(os.environ.get("CARINA_SKIP_GUI") == "1", reason="sem GUI")
def test_app_opens_and_renders(tmp_path):
    out = tmp_path / "fumaca.png"
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONPATH=str(ROOT / "src"))
    env.pop("QT_QPA_PLATFORM", None)   # precisa da janela real para o OpenGL
    proc = subprocess.run(
        [sys.executable, "-m", "carina", "--screenshot", str(out),
         "--size", "640x480", "--at", "2026-10-02T21:00"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=180,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert out.exists() and out.stat().st_size > 10_000
