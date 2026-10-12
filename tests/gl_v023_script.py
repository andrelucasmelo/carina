"""Verificações que desenham o céu com OpenGL (v0.23 — tours), rodadas num
subprocesso com a plataforma real do Qt — a plataforma "offscreen" da
suíte não tem framebuffer OpenGL. Dados do usuário isolados em ``argv[1]``.

Imprime um JSON com o que foi gerado.
"""

import datetime as dt
import json
import sys
from pathlib import Path

out_dir = Path(sys.argv[1])
from PySide6.QtCore import QSettings  # noqa: E402

QSettings.setDefaultFormat(QSettings.IniFormat)
QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(out_dir / "ini"))
import carina.config as cfg  # noqa: E402

cfg.user_data_dir = lambda *a, **k: str(out_dir / "data")
cfg.user_cache_dir = lambda *a, **k: str(out_dir / "cache")

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv[:1])
app.setApplicationName("Carina")
app.setOrganizationName("Carina")
from carina.core import userdata  # noqa: E402

userdata.set_instance(userdata.UserData(out_dir / "u.sqlite"))
from carina.ui.mainwindow import MainWindow  # noqa: E402

UTC = dt.timezone.utc
win = MainWindow()
win.skip_state_save = True
win.resize(1000, 700)
win.show()
result = {}


def run():
    from carina.core.tours import Tour

    sky = win.sky
    sky.moon_sync_load = True
    tour = Tour.from_dict({
        "key": "teste-gl-v023", "title": "Teste", "category": "extra",
        "when": "data:05-15 hora:21:00", "steps": [
            {"title": "Polo", "text": "Seta.", "target": "alignment:cruzeiro-polo",
             "fov": 70},
            {"title": "Lua", "text": "Tycho.", "target": "body:Lua", "fov": 0.6,
             "moon_feature": "Tycho", "time": "em:2026-10-19T19:00",
             "skip_if_below": -90},
        ]})
    win.start_tour(tour, dt.datetime(2026, 5, 15, 23, 0, tzinfo=UTC))
    player = win.tour_player()
    player.finish_animation()
    img = sky.grabFramebuffer()
    result["alignment_frame"] = [img.width(), img.height(),
                                 ("alignment", "cruzeiro-polo") in sky.active_highlights()]
    player.next()
    player.finish_animation()
    sky.grabFramebuffer()
    sky.grabFramebuffer()
    pos = sky.moon_feature_position("Tycho")
    result["moon_marker"] = sky.moon_marker
    result["tycho"] = None if pos is None else [round(pos[1]), round(pos[2]), round(pos[3])]
    result["moon_r"] = round(sky._moon_view["r"]) if sky._moon_view else 0
    player.stop(False)
    result["after"] = [sky.moon_marker, list(sky.active_highlights())]
    print("RESULT " + json.dumps(result))
    app.quit()


QTimer.singleShot(1000, run)
app.exec()
