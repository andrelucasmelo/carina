"""Hora local do OBSERVADOR, não a do computador.

Quando o usuário escolhe uma cidade em outro fuso (por exemplo, planeja uma
viagem ao Atacama a partir do Rio), todos os horários exibidos — barra de
estado, crepúsculos, rastreamento, maratonas — devem estar no fuso da
cidade escolhida, senão o roteiro fica inutilizável no campo.

O módulo guarda o fuso ativo em uma variável global simples: o aplicativo
tem um único observador por vez, e enfiar o fuso por parâmetro em cada
janela/rota de formatação espalharia ruído por todo o código. Chame
:func:`set_timezone` sempre que a localização mudar e :func:`to_local` em
todo lugar que antes usava ``datetime.astimezone()``.
"""

from __future__ import annotations

import datetime as dt

_TZ: dt.tzinfo | None = None


def set_timezone(name: str | None) -> None:
    """Define o fuso ativo a partir do nome IANA (ex.: 'America/Sao_Paulo').

    Nome vazio, ``None`` ou desconhecido caem no fuso do sistema — o
    comportamento antigo, e o correto quando o usuário digita coordenadas
    manuais sem escolher cidade.
    """
    global _TZ
    if not name:
        _TZ = None
        return
    try:
        from zoneinfo import ZoneInfo

        _TZ = ZoneInfo(name)
    except Exception:  # ZoneInfoNotFoundError, tzdata ausente…
        _TZ = None


def timezone_name() -> str:
    """Nome do fuso ativo para exibição ('' quando é o do sistema)."""
    return getattr(_TZ, "key", "") if _TZ is not None else ""


def to_local(value: dt.datetime) -> dt.datetime:
    """Converte um datetime (tipicamente UTC) para a hora do observador."""
    return value.astimezone(_TZ)


def now_local() -> dt.datetime:
    """O "agora" já convertido para a hora do observador."""
    return dt.datetime.now(dt.timezone.utc).astimezone(_TZ)


def from_local_naive(value: dt.datetime) -> dt.datetime:
    """Interpreta um datetime sem fuso como hora local do observador.

    Usado quando o usuário digita uma data/hora (diálogo de tempo): "22:00"
    significa 22:00 na cidade escolhida, não no relógio do computador.
    """
    if _TZ is not None:
        return value.replace(tzinfo=_TZ)
    return value.astimezone()  # sem cidade: assume o fuso do sistema
