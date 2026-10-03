"""Base lunar embarcada (v0.17 T1): arquivos, contagens e orçamento."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MOON = ROOT / "data" / "processed" / "moon"
EPHEM = ROOT / "data" / "ephemeris"


def test_files_and_budget():
    files = ["moon_color.jpg", "moon_normal.jpg", "moon_features.json", "lunar100.json"]
    total = 0
    for name in files:
        p = MOON / name
        assert p.exists(), name
        total += p.stat().st_size
    for k in ("moon_080317.tf", "pck00008.tpc", "moon_pa_de421_1900-2050.bpc"):
        assert (EPHEM / k).exists(), k
        total += (EPHEM / k).stat().st_size
    assert total < 35e6


def test_texture_sizes():
    from PySide6.QtGui import QImageReader

    assert QImageReader(str(MOON / "moon_color.jpg")).size().width() == 8192
    size = QImageReader(str(MOON / "moon_normal.jpg")).size()
    assert (size.width(), size.height()) == (4096, 2048)


def test_counts():
    feats = json.loads((MOON / "moon_features.json").read_text(encoding="utf-8"))
    assert feats["meta"]["count"] == len(feats["features"]) >= 600
    l100 = json.loads((MOON / "lunar100.json").read_text(encoding="utf-8"))["items"]
    assert [i["n"] for i in l100] == list(range(1, 101))
    met = json.loads((ROOT / "data" / "processed" / "meteors.json")
                     .read_text(encoding="utf-8"))["showers"]
    codes = {s["code"] for s in met}
    assert {"PER", "GEM", "ETA", "QUA", "ORI", "LEO", "SDA"} <= codes
    for s in met:
        assert 0 <= s["peak"] < 360 and -90 <= s["dec"] <= 90
