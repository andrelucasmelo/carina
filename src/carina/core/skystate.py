"""Fotografia do estado do céu para os tours (v0.20 T1).

Um tour mexe no relógio, na câmera, nas camadas, no Bortle, na seleção e
nos destaques. Ao sair — no fim, no meio ou por ``Esc`` — o céu tem de
voltar **exatamente** como estava. :class:`SkyState` captura tudo isso de
uma vez e restaura de uma vez; o teste de identidade fica em
``tests/test_tours.py``.

O relógio volta ao modo em que estava: tempo real continua tempo real
(com o "agora" de quando o tour termina), um instante pausado volta ao
mesmo instante, uma simulação acelerada volta à mesma data e velocidade.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

UTC = dt.timezone.utc
REALTIME_TOLERANCE_S = 90.0


@dataclass
class SkyState:
    render: object                     # RenderOptions
    theme: str
    camera: tuple[float, float, float]  # az, alt, fov (rad)
    selection: tuple | None
    follow: bool
    fov_shapes: list = field(default_factory=list)
    fov_angle: float = 0.0
    fov_follow: bool = True
    sim_time: dt.datetime | None = None
    speed: float = 1.0
    realtime: bool = True

    @classmethod
    def capture(cls, sky, engine) -> "SkyState":
        clock = engine.time
        sim = clock.current_datetime()
        now = dt.datetime.now(UTC)
        realtime = clock.speed == 1.0 and abs((sim - now).total_seconds()) < REALTIME_TOLERANCE_S
        cam = sky.camera
        return cls(render=sky.render_options(), theme=getattr(sky, "theme", "dark"),
                   camera=(cam.az, cam.alt, cam.fov), selection=sky.selection,
                   follow=bool(getattr(sky, "follow_selection", False)),
                   fov_shapes=list(getattr(sky, "fov_shapes", [])),
                   fov_angle=float(getattr(sky, "fov_angle", 0.0)),
                   fov_follow=bool(getattr(sky, "fov_follow_selection", True)),
                   sim_time=sim, speed=clock.speed, realtime=realtime)

    def restore(self, sky, engine) -> None:
        anim = getattr(sky, "_goto_anim", None)
        if anim is not None:
            anim.stop()
        if hasattr(sky, "clear_highlights"):
            sky.clear_highlights()
        if getattr(sky, "theme", self.theme) != self.theme and hasattr(sky, "set_theme"):
            sky.set_theme(self.theme)
        sky.apply_render_options(self.render)
        az, alt, fov = self.camera
        sky.camera.fov = fov
        sky.camera.set_direction(az, alt)
        if sky.selection != self.selection:
            sky.selection = self.selection
            if hasattr(sky, "selectionChanged"):
                sky.selectionChanged.emit(self.selection)
        if hasattr(sky, "follow_selection"):
            sky.follow_selection = self.follow
        sky.fov_shapes = list(self.fov_shapes)
        sky.fov_angle = self.fov_angle
        sky.fov_follow_selection = self.fov_follow
        clock = engine.time
        if self.realtime:
            clock.to_now()
        else:
            clock.set_datetime(self.sim_time)
            clock.set_speed(self.speed)
        sky.update()

    def same_as(self, other: "SkyState") -> list[str]:
        """Diferenças (para os testes): lista vazia = idênticos."""
        diffs = []
        if self.render != other.render:
            diffs.append("render")
        for name in ("theme", "selection", "follow", "fov_angle", "fov_follow", "realtime"):
            if getattr(self, name) != getattr(other, name):
                diffs.append(name)
        if any(abs(a - b) > 1e-6 for a, b in zip(self.camera, other.camera)):
            diffs.append("camera")
        if len(self.fov_shapes) != len(other.fov_shapes):
            diffs.append("fov_shapes")
        if not self.realtime:
            if abs((self.sim_time - other.sim_time).total_seconds()) > 1 or self.speed != other.speed:
                diffs.append("time")
        return diffs
