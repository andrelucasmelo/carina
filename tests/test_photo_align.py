"""Alinhamento de foto por duas estrelas (v0.19 T4)."""

import math

import numpy as np
import pytest


def _vec(ra_deg, dec_deg):
    ra, dec = math.radians(ra_deg), math.radians(dec_deg)
    return np.array([math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra), math.sin(dec)])


@pytest.mark.parametrize("mirror", [False, True])
@pytest.mark.parametrize("rot_deg,scale", [(0.0, 2.0), (37.0, 5.5), (200.0, 30.0)])
def test_recovers_synthetic_transform(mirror, rot_deg, scale):
    """Gera uma foto sintética (escala, rotação, translação), marca duas
    estrelas e confere que uma terceira cai no pixel certo."""
    from carina.core.photo_align import PhotoAlignment, _basis, solve

    t, e, n = _basis(_vec(83.8, -5.4))                 # Órion
    a_true = complex(math.cos(math.radians(rot_deg)), math.sin(math.radians(rot_deg))) \
        * math.radians(scale / 3600.0)
    # o ponto tangente (centro óptico) é o centro da imagem 1600×1000
    zc = complex(800.0, -500.0)
    b_true = -a_true * (zc.conjugate() if mirror else zc)
    truth = PhotoAlignment(a_true, b_true, t, e, n, mirror)
    pix = [(120.0, 340.0), (1500.0, 900.0), (800.0, 100.0)]
    stars = [truth.pixel_to_icrs(x, y) for x, y in pix]
    al = solve(pix[0], pix[1], stars[0], stars[1], mirror=mirror, center=(800.0, 500.0))
    x, y = al.icrs_to_pixel(stars[2])
    assert x == pytest.approx(pix[2][0], abs=0.05) and y == pytest.approx(pix[2][1], abs=0.05)
    assert al.scale_arcsec == pytest.approx(scale, rel=1e-3)
    back = PhotoAlignment.from_dict(al.to_dict())
    assert np.allclose(back.pixel_to_icrs(10.0, 20.0), al.pixel_to_icrs(10.0, 20.0))


def test_grid_and_errors():
    from carina.core.photo_align import solve

    al = solve((0, 0), (100, 0), _vec(10, 0), _vec(10.1, 0))
    verts, uv = al.grid(200, 100, 5)
    assert verts.shape == (25, 3) and uv.shape == (25, 2)
    assert np.allclose(np.linalg.norm(verts, axis=1), 1.0)
    with pytest.raises(ValueError):
        solve((5, 5), (5, 5), _vec(10, 0), _vec(11, 0))


def test_dialog_aligns_and_saves(tmp_path, isolated_userdata):
    """Foto sintética com Betelgeuse e Rigel nos pixels certos."""
    from PySide6.QtGui import QColor, QImage

    from carina.catalogs.stars import StarCatalog
    from carina.config import package_data_dir
    from carina.ui.photo_overlay import PHOTO_KIND, PhotoOverlayDialog

    img = QImage(800, 600, QImage.Format_RGB888)
    img.fill(QColor(5, 5, 10))
    path = str(tmp_path / "orion.png")
    img.save(path)
    stars = StarCatalog(package_data_dir())
    dlg = PhotoOverlayDialog(stars, userdata=isolated_userdata)
    assert dlg.load(path)
    dlg.mark("A", 200.0, 100.0)
    dlg.mark("B", 600.0, 500.0)
    dlg.cb_a.setEditText("Betelgeuse")
    dlg.cb_b.setEditText("Rigel")
    ov = dlg.apply()
    assert ov is not None and ov.width == 800
    # Betelgeuse–Rigel ≈ 18,6°; 566 px entre os pontos → ~118″/px
    assert 110 < ov.alignment.scale_arcsec < 125
    assert isolated_userdata.profile(PHOTO_KIND, "atual")["path"] == path
    dlg.close()
