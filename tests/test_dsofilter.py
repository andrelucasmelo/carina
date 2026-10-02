"""Filtro de exibição do céu profundo (§9 da revisão 2026-10)."""

import numpy as np
import pytest

from carina.catalogs.dso import ALL_CATALOGS, KLASS_CODES
from carina.core.dsofilter import PRESETS, DsoFilter


class FakeDso:
    """Arrays de render mínimos: 6 objetos."""

    def __init__(self):
        #            M42   NGC7000  LDN1  Sh2-276  user  faint gal
        self.mag = np.array([4.0, 4.0, 99.0, 99.0, 9.0, 12.5], dtype=np.float32)
        self.maj = np.array([90.0, 120.0, 30.0, 600.0, 0.0, 2.0], dtype=np.float32)
        self.klass = np.array([KLASS_CODES[k] for k in
                               ("NEB", "NEB", "DARK", "NEB", "OTHER", "GAL")], dtype=np.int8)
        self.cat_matrix = np.zeros((6, len(ALL_CATALOGS)), dtype=bool)
        for i, cats in enumerate((("M", "NGC"), ("NGC", "C"), ("LDN",), ("SH2",), (), ("NGC",))):
            for c in cats:
                self.cat_matrix[i, ALL_CATALOGS.index(c)] = True
        self.has_common = np.array([True, True, False, False, False, False])
        self.is_mc = np.array([True, True, False, False, False, False])


@pytest.fixture
def dso():
    return FakeDso()


def test_default_hides_extra_catalogs_but_keeps_user_objects(dso):
    keep = DsoFilter().mask(dso)
    assert keep.tolist() == [True, True, False, True, True, True]


def test_catalog_and_class_filters(dso):
    f = DsoFilter(catalogs=set(ALL_CATALOGS), classes={"DARK"})
    assert f.mask(dso).tolist() == [False, False, True, False, False, False]


def test_magnitude_range_and_unknown_handling(dso):
    f = DsoFilter(mag_max=8.0, include_unknown_mag=False)
    assert f.mask(dso).tolist() == [True, True, False, False, False, False]
    f.include_unknown_mag = True
    assert f.mask(dso).tolist() == [True, True, False, True, False, False]


def test_size_range(dso):
    f = DsoFilter(size_min=60.0, size_max=200.0, include_unknown_size=False)
    assert f.mask(dso).tolist() == [True, True, False, False, False, False]


def test_only_named_and_only_mc(dso):
    assert DsoFilter(only_named=True).mask(dso).sum() == 2
    assert DsoFilter(only_mc=True).mask(dso).sum() == 2


def test_big_regions_hidden_only_in_wide_fields(dso):
    f = DsoFilter(big_mode="hide", big_threshold_arcmin=120.0, big_hide_fov_deg=40.0)
    assert f.big_mask(dso).tolist() == [False, True, False, True, False, False]
    assert f.mask(dso, fov_deg=60.0).tolist() == [True, False, False, False, True, True]
    assert f.mask(dso, fov_deg=20.0).tolist() == [True, True, False, True, True, True]
    assert f.mask(dso).tolist() == [True, True, False, True, True, True]


def test_json_round_trip_and_bad_input():
    f = DsoFilter(catalogs={"M", "C"}, mag_max=7.5, big_mode="label", only_named=True)
    g = DsoFilter.from_json(f.to_json())
    assert g == f
    assert DsoFilter.from_json("") == DsoFilter()
    assert DsoFilter.from_json("{nao é json") == DsoFilter()
    h = DsoFilter.from_json('{"big_mode": "xyz", "mag_max": 5}')
    assert h.big_mode == "outline" and h.mag_max == 5


def test_presets_are_distinct_and_default_matches(dso):
    assert PRESETS["Padrão"] == DsoFilter()
    assert PRESETS["Só Messier e Caldwell"].mask(dso).sum() == 2
    assert PRESETS["Tudo"].mask(dso).sum() == 6
    # objeto do usuário (sem catálogo) continua: mag 9 cabe no corte
    assert PRESETS["Binóculo"].mask(dso).tolist() == [True, True, False, False, True, False]


def test_catalog_menu_toggles_whole_catalogs(qt_app):
    """Pré-0.17: Exibir ▸ Objetos ▸ Catálogos liga e desliga catálogos inteiros."""
    from carina.catalogs.dso import ALL_CATALOGS
    from carina.ui.mainwindow import MainWindow

    win = MainWindow()
    win.skip_state_save = True
    original = win.sky.dso_filter.copy()
    try:
        win._set_all_catalogs(True)
        win._fill_catalog_menu()
        acts = [a for a in win._cat_menu.actions() if a.isCheckable()]
        assert len(acts) == len(ALL_CATALOGS) and all(a.isChecked() for a in acts)
        dso = win.dso_catalog
        sh2 = dso.cat_matrix[:, ALL_CATALOGS.index("SH2")]
        only_sh2 = sh2 & (dso.cat_matrix.sum(axis=1) == 1)
        assert only_sh2.any()
        win._set_catalog_visible("SH2", False)
        mask = win.sky.dso_filter.mask(dso)
        assert not mask[only_sh2].any()                 # Sh2 sozinhos somem
        win._set_all_catalogs(False)
        mask = win.sky.dso_filter.mask(dso)
        assert mask[dso.cat_matrix.any(axis=1)].sum() == 0
    finally:
        win._apply_dso_filter(original)
        win.close()
