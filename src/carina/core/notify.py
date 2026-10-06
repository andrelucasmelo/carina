"""Lembretes do Windows (v0.22 T6).

Com o programa aberto, os lembretes do Calendário do céu (🔔) viram uma
notificação do Windows **uma hora antes** do evento (a mesma antecedência
do alarme do .ics). A decisão de quando avisar fica aqui, sem Qt; quem
mostra é a janela principal — pelo ícone de bandeja do Qt (notificação
nativa) ou, se não houver bandeja, pelo PowerShell.

Cada lembrete avisa **uma vez**: os avisados ficam guardados (UID) e os
antigos são esquecidos depois de dois dias.
"""

from __future__ import annotations

import datetime as dt
import shutil
import subprocess
import sys

LEAD_MINUTES = 60


def due_now(reminders: list, now_utc: dt.datetime, notified: set[str],
            lead_minutes: float = LEAD_MINUTES) -> list:
    """Lembretes que devem avisar agora: dentro da antecedência, ainda não
    passados há mais de 30 min e não avisados."""
    out = []
    for ev in reminders:
        if ev.uid in notified:
            continue
        start = ev.start_utc
        if start - dt.timedelta(minutes=lead_minutes) <= now_utc <= start + dt.timedelta(minutes=30):
            out.append(ev)
    return out


def message_for(ev, now_utc: dt.datetime) -> tuple[str, str]:
    from .localtime import to_local

    mins = int(round((ev.start_utc - now_utc).total_seconds() / 60))
    when = f"às {to_local(ev.start_utc):%H:%M}"
    lead = (f"em {mins} min" if mins > 0 else "agora")
    return f"Carina — {ev.title}", f"{lead.capitalize()} ({when}). {ev.detail or ''}".strip()


def powershell_toast(title: str, body: str) -> bool:
    """Notificação do Windows pelo PowerShell (sem módulos extras)."""
    if sys.platform != "win32":
        return False
    exe = shutil.which("powershell") or shutil.which("powershell.exe")
    if exe is None:
        return False
    script = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
        "ContentType = WindowsRuntime] > $null; "
        "$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
        "[Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
        "$x = $t.GetElementsByTagName('text'); "
        "$x.Item(0).AppendChild($t.CreateTextNode($env:CARINA_TITLE)) > $null; "
        "$x.Item(1).AppendChild($t.CreateTextNode($env:CARINA_BODY)) > $null; "
        "$n = [Windows.UI.Notifications.ToastNotification]::new($t); "
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
        "'{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe'"
        ").Show($n)")
    import os

    env = dict(os.environ, CARINA_TITLE=title, CARINA_BODY=body)
    try:
        subprocess.Popen([exe, "-NoProfile", "-NonInteractive", "-Command", script],
                         env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return True
    except OSError:
        return False
