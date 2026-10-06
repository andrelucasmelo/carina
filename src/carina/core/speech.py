"""Narração dos tours pela voz do Windows (v0.21 T6, experimental).

Usa o sintetizador de voz do próprio Windows (``System.Speech``, via
PowerShell) — nenhuma dependência nova, nada é baixado. O texto vai pela
entrada padrão do processo, então aspas e acentos não precisam de escape.
Fica desligado por padrão (Tours ▸ painel ▸ 🔊); se o PowerShell ou a voz
não existirem, ``say`` simplesmente não faz nada.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys

_PS = ("Add-Type -AssemblyName System.Speech; "
       "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
       "try { $s.SelectVoiceByHints('NotSet', 'NotSet', 0, "
       "[System.Globalization.CultureInfo]'pt-BR') } catch {}; "
       "$s.Rate = 0; "
       "[Console]::InputEncoding = [System.Text.Encoding]::UTF8; "
       "$s.Speak([Console]::In.ReadToEnd())")


def plain_text(markdown: str) -> str:
    """Markdown → texto corrido para a voz (sem asteriscos, crases e listas)."""
    t = re.sub(r"`([^`]*)`", r"\1", markdown)
    t = re.sub(r"\*\*|__|\*|_", "", t)
    t = re.sub(r"^\s*[-•]\s+", "", t, flags=re.M)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    t = t.replace("▸", ",").replace("→", "a").replace("°", " graus")
    return re.sub(r"\s+", " ", t).strip()


def powershell() -> str | None:
    if sys.platform != "win32":
        return None
    return shutil.which("powershell") or shutil.which("powershell.exe")


class Speaker:
    """Uma fala por vez: ``say`` interrompe a anterior."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None

    @staticmethod
    def available() -> bool:
        return powershell() is not None

    def say(self, markdown: str) -> bool:
        self.stop()
        exe = powershell()
        text = plain_text(markdown)
        if exe is None or not text:
            return False
        try:
            self._proc = subprocess.Popen(
                [exe, "-NoProfile", "-NonInteractive", "-Command", _PS],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self._proc.stdin.write(text.encode("utf-8"))
            self._proc.stdin.close()
            return True
        except OSError:
            self._proc = None
            return False

    def speaking(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def stop(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            try:
                self._proc.kill()
            except OSError:
                pass
        self._proc = None
