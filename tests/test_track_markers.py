"""Rastreamento (correção pré-0.16): marcador a cada 30 min dentro da
carta e rótulos "19h" nas horas cheias — inclusive perto do polo sul
(NGC 104), onde os pontos saíam da carta depois do primeiro rótulo."""

import datetime as dt
import math
from pathlib import Path

import pytest

EPHEM = Path(__file__).resolve().parent.parent / "data" / "ephemeris"


@pytest.mark.parametrize("ra_h,dec_d", [(0.401, -72.08), (5.588, -5.39)],
                         ids=["NGC104", "M42"])
def test_markers_inside_chart(ra_h, dec_d):
    if not (EPHEM / "de440s.bsp").exists():
        pytest.skip("efeméride ausente")
    import numpy as np
    from PySide6.QtCore import QPointF, QRectF
    from PySide6.QtGui import QImage, QPainter

    from carina.config import ObserverLocation
    from carina.core.engine import SkyEngine
    from carina.core.localtime import to_local
    from carina.core.tracking import compute_track
    from carina.ui.track_window import TrackCanvas, TrackSettings

    e = SkyEngine(EPHEM)
    e.set_location(ObserverLocation())
    ra, dec = math.radians(ra_h * 15), math.radians(dec_d)
    vec = np.array([math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra),
                    math.sin(dec)])
    ref = dt.datetime(2026, 12, 20, 3, tzinfo=dt.timezone.utc)
    res = compute_track(e, ("dso", 0), "alvo", vec, ref)
    settings = TrackSettings()
    canvas = TrackCanvas(res, settings, "Rio")

    centers, texts = [], []

    class Recorder(QPainter):
        def drawEllipse(self, *args):
            if args and isinstance(args[0], QPointF):
                centers.append(args[0])
            return super().drawEllipse(*args)

        def drawText(self, *args):
            texts.append(args[-1])
            return super().drawText(*args)

    img = QImage(1000, 1000, QImage.Format_RGB32)
    p = Recorder(img)
    canvas.render_to(p, QRectF(0, 0, 1000, 1000))
    p.end()

    expected = sum(1 for pt in res.points
                   if (to_local(pt.when_utc).hour * 60 + to_local(pt.when_utc).minute) % 30 == 0)
    markers = [c for c in centers if 0 <= c.x() <= 1000 and 0 <= c.y() <= 1000]
    assert expected >= 6
    assert len(markers) >= expected            # nenhum marcador sumiu da carta
    hours = [t for t in texts if isinstance(t, str) and t.endswith("h") and t[:-1].isdigit()]
    assert len(hours) >= expected // 2 - 2     # rótulos de hora cheia "19h"
