"""Verificações que desenham o céu com OpenGL (v0.22), rodadas num
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
    from carina.core.report import build_report
    from carina.ui.night_report import make_card_png, make_report_pdf
    from carina.ui.planisphere import PlanisphereDialog
    from carina.ui.poster_dialog import PosterSpec, render_poster, save_poster

    ud = win.userdata
    ud.add_observation("dso", "NGC 253", "NGC 253", dt.datetime(2026, 10, 6, 23, tzinfo=UTC))
    rep = build_report(win.engine, ud, dt.date(2026, 10, 6), "Rio")
    make_report_pdf(out_dir / "r.pdf", win.sky, rep)
    card = make_card_png(out_dir / "c.png", win.sky, rep)
    result["report_bytes"] = (out_dir / "r.pdf").stat().st_size
    result["card"] = [card.width(), card.height(), (out_dir / "c.png").stat().st_size]
    when = dt.datetime(2026, 10, 6, 0, 0, tzinfo=UTC)
    img = render_poster(win.sky, PosterSpec("Teste", "frase", when, "Rio", "A3", "dark"), dpi=40)
    result["poster"] = [img.width(), img.height()]
    save_poster(str(out_dir / "p.pdf"), win.sky, PosterSpec("T", "", when, "Rio", "A4", "light"),
                dpi=60)
    result["poster_pdf"] = (out_dir / "p.pdf").read_bytes()[:5].decode("latin1")
    dlg = PlanisphereDialog(win)
    dlg.set_time(when)
    result["planis_edit"] = dlg.edit.dateTime().toPython().isoformat()
    dlg._to_sky()
    result["sky_time"] = win.engine.time.current_datetime().isoformat()
    dlg.close()
    win.sky.set_layer("sun_path", True)
    win.sky.grabFramebuffer()
    _key, path, ana = win.sky._sun_path_cache
    result["sun_path"] = [len(path.verts), len(ana.verts)]
    print("RESULT " + json.dumps(result))
    app.quit()


QTimer.singleShot(1000, run)
app.exec()
