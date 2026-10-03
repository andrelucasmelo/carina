"""Otimizações da Lua (v0.17.1): pirâmide, envio em etapas, interpolação."""

import numpy as np
import pytest


def test_bilinear_matches_reference():
    from carina.render.moon_cpu import _bilinear

    rng = np.random.default_rng(1)
    tex = rng.integers(0, 256, (64, 128, 3), dtype=np.uint8)
    u = rng.random(500).astype(np.float32)
    v = rng.random(500).astype(np.float32)
    got = _bilinear(tex, u, v)
    # referência direta em float64, com a costura em longitude
    h, w, _ = tex.shape
    x = u * w - 0.5
    y = np.clip(v * h - 0.5, 0, h - 1.001)
    x0 = np.floor(x).astype(int)
    y0 = np.floor(y).astype(int)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    t = tex.astype(np.float64)
    ref = ((t[y0, x0 % w] * (1 - fx) + t[y0, (x0 + 1) % w] * fx) * (1 - fy)
           + (t[np.minimum(y0 + 1, h - 1), x0 % w] * (1 - fx)
              + t[np.minimum(y0 + 1, h - 1), (x0 + 1) % w] * fx) * fy)
    assert got.dtype == np.float32
    assert np.allclose(got, ref, atol=0.05)


def test_mip_chain_and_level_choice():
    from carina.render import moontex

    chain = moontex.mip_chain(np.zeros((512, 1024, 3), np.uint8))
    assert [lv.shape[1] for lv in chain] == [1024, 512, 256, 128, 64, 32, 16]
    assert moontex.level_for(900) == 3          # 1024 px basta
    assert moontex.level_for(3000) == 1         # 4096
    assert moontex.level_for(20000) == 0        # 8192 no zoom extremo


def test_scaled_decode_and_upload_plan():
    from carina.render import moontex

    if not moontex.available():
        pytest.skip("dados lunares ausentes")
    lv = moontex.level(3)
    assert lv[0].shape[1] == 1024 and lv[1].shape[1] >= 1024
    plan = moontex.gpu_upload_plan()
    kinds = [k for k, _ in plan]
    assert kinds == ["color", "normal", "normal", "color"]
    # a prévia é pequena; a cor completa para em 4096 (8k só sob demanda)
    assert plan[0][1][0].shape[1] <= 2048 and plan[1][1][0].shape[1] <= 2048
    assert plan[3][1][0].shape[1] == 4096
    for _k, levels in plan:
        widths = [x.shape[1] for x in levels]
        assert widths == sorted(widths, reverse=True)
    moontex.release_cpu_levels()


def test_render_only_touches_disc_box():
    from carina.render.moon_cpu import MoonView, render

    color = np.full((64, 128, 3), 200, np.uint8)
    normal = np.full((32, 64, 3), (128, 128, 255), np.uint8)
    view = MoonView(400, 300, zoom=0.5)          # disco pequeno no centro
    img = render(view, np.eye(3), np.array([0.0, 0.0, 1.0]), np.array([0.0, 0.0, 1.0]),
                 color, normal, background=(1, 2, 3))
    assert tuple(img[0, 0]) == (1, 2, 3) and tuple(img[150, 5]) == (1, 2, 3)
    assert img[150, 200].mean() > 100            # centro iluminado
