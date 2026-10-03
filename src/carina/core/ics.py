"""Gerador (e leitor mínimo) de iCalendar — RFC 5545, sem dependências.

O Calendário do céu exporta os eventos para um ``.ics`` que o Google
Agenda, o Outlook e o calendário do celular importam. Escrevemos só o
subconjunto necessário: ``VCALENDAR`` com ``VEVENT`` (UID estável,
``DTSTAMP``, ``DTSTART``/``DTEND`` em UTC, ``SUMMARY``, ``DESCRIPTION``,
``CATEGORIES``, ``LOCATION``) e, opcionalmente, um ``VALARM`` de aviso.

Regras que os importadores cobram: linhas terminadas em CRLF, dobradas a
75 octetos (continuação começa com espaço), e vírgula, ponto e vírgula,
barra invertida e quebra de linha escapados nos textos.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

PRODID = "-//Carina//Calendario do ceu//PT-BR"


def escape(text: str) -> str:
    return (text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def unescape(text: str) -> str:
    out, i = [], 0
    while i < len(text):
        c = text[i]
        if c == "\\" and i + 1 < len(text):
            nxt = text[i + 1]
            out.append("\n" if nxt in "nN" else nxt)
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def fold(line: str) -> str:
    """Dobra uma linha em pedaços de até 75 octetos UTF-8."""
    data = line.encode("utf-8")
    if len(data) <= 75:
        return line
    parts, cur, size = [], [], 0
    limit = 75
    for ch in line:
        n = len(ch.encode("utf-8"))
        if size + n > limit:
            parts.append("".join(cur))
            cur, size, limit = [], 0, 74     # continuação: 1 octeto do espaço
        cur.append(ch)
        size += n
    parts.append("".join(cur))
    return "\r\n ".join(parts)


def _stamp(when: dt.datetime) -> str:
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.timezone.utc)
    return when.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


@dataclass
class IcsEvent:
    uid: str
    start_utc: dt.datetime
    summary: str
    description: str = ""
    end_utc: dt.datetime | None = None
    category: str = ""
    location: str = ""
    alarm_minutes: int | None = None


def to_ics(events: list[IcsEvent], name: str = "Carina — Calendário do céu",
           now: dt.datetime | None = None) -> str:
    now = now or dt.datetime.now(dt.timezone.utc)
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH", f"X-WR-CALNAME:{escape(name)}"]
    for ev in events:
        end = ev.end_utc or (ev.start_utc + dt.timedelta(minutes=30))
        lines += [
            "BEGIN:VEVENT",
            f"UID:{ev.uid}@carina",
            f"DTSTAMP:{_stamp(now)}",
            f"DTSTART:{_stamp(ev.start_utc)}",
            f"DTEND:{_stamp(end)}",
            f"SUMMARY:{escape(ev.summary)}",
        ]
        if ev.description:
            lines.append(f"DESCRIPTION:{escape(ev.description)}")
        if ev.category:
            lines.append(f"CATEGORIES:{escape(ev.category)}")
        if ev.location:
            lines.append(f"LOCATION:{escape(ev.location)}")
        if ev.alarm_minutes is not None:
            lines += ["BEGIN:VALARM", "ACTION:DISPLAY",
                      f"DESCRIPTION:{escape(ev.summary)}",
                      f"TRIGGER:-PT{int(ev.alarm_minutes)}M", "END:VALARM"]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(line) for line in lines) + "\r\n"


def parse_ics(text: str) -> list[dict]:
    """Leitor mínimo (testes e conferência): devolve os VEVENTs como
    dicionários ``{propriedade: valor}`` já desdobrados e sem escape."""
    raw = text.replace("\r\n", "\n").split("\n")
    lines: list[str] = []
    for line in raw:
        if line.startswith((" ", "\t")) and lines:
            lines[-1] += line[1:]
        elif line:
            lines.append(line)
    events, cur, depth = [], None, []
    for line in lines:
        key, _, value = line.partition(":")
        name = key.split(";")[0].upper()
        if name == "BEGIN":
            depth.append(value)
            if value == "VEVENT":
                cur = {}
            continue
        if name == "END":
            if depth and depth[-1] == value:
                depth.pop()
            if value == "VEVENT" and cur is not None:
                events.append(cur)
                cur = None
            continue
        if cur is not None and depth and depth[-1] == "VEVENT":
            cur[name] = unescape(value)
    return events


def parse_stamp(value: str) -> dt.datetime:
    return dt.datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc)
