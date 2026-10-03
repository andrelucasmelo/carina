"""Desenho dos planetas na CPU (v0.18): disco, fase, anéis e sombras.

Para cada pixel, um raio paralelo à linha de visada (projeção ortográfica,
em raios equatoriais) é intersectado com o **elipsoide** do planeta
(achatamento real: Júpiter 6,5%, Saturno 9,8%) e, em Saturno, com o
**plano dos anéis**. O que fica na frente vence; o anel atrás do planeta
some. A luz vem da direção real do Sol, então Mercúrio e Vênus aparecem
na fase certa, Marte com a gibosidade e Saturno com:

- a sombra do planeta sobre os anéis (atrás do globo, no lado oposto ao Sol);
- a sombra dos anéis sobre o globo.

Luas e suas sombras (Júpiter) são desenhadas por cima, como discos.

Coordenadas locais da vista: a = leste, b = norte, c = para o observador,
em raios equatoriais — as mesmas de :class:`render.moon_cpu.MoonView`.
"""

from __future__ import annotations

import math

import numpy as np

from .moon_cpu import MoonView, _bilinear


def view_basis(u_icrs: np.ndarray):
    """(e_t, n_t, w): leste, norte e direção do observador no planeta."""
    u = u_icrs / np.linalg.norm(u_icrs)
    pole = np.array([0.0, 0.0, 1.0])
    n_t = pole - (pole @ u) * u
    n_t /= np.linalg.norm(n_t)
    e_t = np.cross(pole, u)
    e_t /= np.linalg.norm(e_t)
    return e_t, n_t, -u


def render_planet(view: MoonView, frame: np.ndarray, u_icrs: np.ndarray,
                  sun_dir: np.ndarray, texture: np.ndarray | None,
                  flattening: float, tex_offset_u: float = 0.0,
                  rings: dict | None = None, gain: float = 1.15,
                  limb_darkening: float = 0.35, background=(6, 8, 14),
                  light_exponent: float = 1.0) -> np.ndarray:
    """Imagem RGB uint8 do planeta.

    ``frame``: linhas X, Y, Z do referencial do planeta em ICRS (a textura
    é aplicada nele). ``flattening`` = raio polar / equatorial.
    ``rings`` (Saturno): {"inner": r, "outer": r (em raios equatoriais),
    "profile": array (N, 4) RGBA uint8 do centro para fora}.
    """
    w, h = int(view.width), int(view.height)
    img = np.empty((h, w, 3), dtype=np.float32)
    img[:] = np.asarray(background, np.float32) / 255.0
    extent = rings["outer"] if rings else 1.0
    cx, cy = view.to_screen(0.0, 0.0)
    r = view.scale * extent * 1.02
    x0, x1 = max(0, int(cx - r)), min(w, int(cx + r) + 2)
    y0, y1 = max(0, int(cy - r)), min(h, int(cy + r) + 2)
    if x0 >= x1 or y0 >= y1:
        return np.clip(img * 255, 0, 255).astype(np.uint8)
    ys, xs = np.mgrid[y0:y1, x0:x1].astype(np.float64)
    a, b = view.to_local(xs.ravel() + 0.5, ys.ravel() + 0.5)
    e_t, n_t, wv = view_basis(u_icrs)
    M = frame @ np.column_stack([e_t, n_t, wv])          # local -> corpo
    sun_b = frame @ (sun_dir / np.linalg.norm(sun_dir))
    view_b = M[:, 2]                                      # direção do observador
    f2 = flattening ** 2
    # raio: origem (a, b, 10) local, direção (0, 0, −1)
    o = (M @ np.stack([a, b, np.full_like(a, 10.0)])).T   # (N, 3) corpo
    d = -view_b
    A = d[0] ** 2 + d[1] ** 2 + d[2] ** 2 / f2
    B = 2 * (o[:, 0] * d[0] + o[:, 1] * d[1] + o[:, 2] * d[2] / f2)
    Cc = o[:, 0] ** 2 + o[:, 1] ** 2 + o[:, 2] ** 2 / f2 - 1.0
    disc = B * B - 4 * A * Cc
    hit = disc > 0
    t_planet = np.full(len(a), np.inf)
    t_planet[hit] = (-B[hit] - np.sqrt(disc[hit])) / (2 * A)
    out = np.zeros((len(a), 3), np.float32)
    alpha = np.zeros(len(a), np.float32)

    # --- globo ---
    idx = np.nonzero(hit)[0]
    if len(idx):
        p = o[idx] + t_planet[idx, None] * d
        nrm = np.stack([p[:, 0], p[:, 1], p[:, 2] / f2], axis=1)
        nrm /= np.linalg.norm(nrm, axis=1, keepdims=True)
        lon = np.arctan2(p[:, 1], p[:, 0])
        lat = np.arctan2(p[:, 2], np.hypot(p[:, 0], p[:, 1]) * f2)   # planetográfica
        if texture is not None:
            u = (lon / (2 * np.pi) + 0.5 + tex_offset_u) % 1.0
            v = 0.5 - lat / np.pi
            alb = _bilinear(texture, u.astype(np.float32), v.astype(np.float32)) / 255.0
        else:
            alb = np.full((len(idx), 3), 0.8, np.float32)
        mu0 = np.clip(nrm @ sun_b, 0.0, 1.0)
        mu = np.clip(nrm @ view_b, 0.0, 1.0)
        # expoente < 1: atmosferas densas (Vênus) espalham a luz e a foice
        # fica brilhante até perto do terminador
        light = mu0 ** light_exponent * (1.0 - limb_darkening + limb_darkening * mu)
        if rings:
            # sombra dos anéis no globo: raio do ponto rumo ao Sol cruza o plano
            with np.errstate(divide="ignore", invalid="ignore"):
                k = -p[:, 2] / sun_b[2]
            q = p + k[:, None] * sun_b
            rr = np.hypot(q[:, 0], q[:, 1])
            shade = (k > 0) & (rr > rings["inner"]) & (rr < rings["outer"])
            if shade.any():
                ra = _ring_alpha(rings, rr[shade])
                light[shade] *= (1.0 - 0.85 * ra)
        out[idx] = alb * (light * gain)[:, None]
        # lado noturno se funde com o fundo (Vênus e Mercúrio em foice);
        # com anéis o globo continua opaco para esconder o anel de trás
        alpha[idx] = 1.0 if rings else np.clip(mu0 * 12.0 + 0.0, 0.0, 1.0)

    # --- anéis ---
    if rings:
        with np.errstate(divide="ignore", invalid="ignore"):
            t_ring = -o[:, 2] / d[2]
        q = o + t_ring[:, None] * d
        rr = np.hypot(q[:, 0], q[:, 1])
        on = (rr > rings["inner"]) & (rr < rings["outer"]) & np.isfinite(t_ring)
        front = on & (t_ring < t_planet)
        ridx = np.nonzero(front)[0]
        if len(ridx):
            rgba = _ring_rgba(rings, rr[ridx])
            # o PNG traz só o brilho: tinge com a cor creme dos anéis
            col = rgba[:, :3].mean(axis=1, keepdims=True) / _ring_peak(rings) * RING_TINT
            ra = rgba[:, 3]
            # iluminação: o lado iluminado depende de B' (Sol); sombra do globo
            lit = np.full(len(ridx), 0.25 + 0.75 * min(1.0, abs(sun_b[2]) * 6.0), np.float32)
            same_side = np.sign(sun_b[2]) == np.sign(view_b[2])
            if not same_side:
                lit *= 0.35                                   # face não iluminada
            qq = q[ridx]
            Bs = 2 * (qq[:, 0] * sun_b[0] + qq[:, 1] * sun_b[1] + qq[:, 2] * sun_b[2] / f2)
            As = sun_b[0] ** 2 + sun_b[1] ** 2 + sun_b[2] ** 2 / f2
            Cs = qq[:, 0] ** 2 + qq[:, 1] ** 2 + qq[:, 2] ** 2 / f2 - 1.0
            ds = Bs * Bs - 4 * As * Cs
            shadowed = (ds > 0) & ((-Bs + np.sqrt(np.maximum(ds, 0))) > 0)
            lit[shadowed] *= 0.08
            c_ring = col * (lit * gain)[:, None]
            out[ridx] = out[ridx] * (1.0 - ra[:, None]) + c_ring * ra[:, None]
            alpha[ridx] = np.maximum(alpha[ridx], ra)
    sub = img[y0:y1, x0:x1].reshape(-1, 3)
    sub[:] = sub * (1.0 - alpha[:, None]) + out * alpha[:, None]
    img[y0:y1, x0:x1] = sub.reshape(y1 - y0, x1 - x0, 3)
    return np.clip(img * 255.0, 0, 255).astype(np.uint8)


RING_TINT = np.array([0.93, 0.86, 0.72], np.float32)


def _ring_peak(rings: dict) -> float:
    """Brilho máximo do perfil onde o anel existe (alfa > 40)."""
    prof = rings["profile"]
    solid = prof[prof[:, 3] > 40, :3]
    return max(float(solid.mean(axis=1).max()) / 255.0, 1e-3) if len(solid) else 1.0


def _ring_rgba(rings: dict, rr: np.ndarray) -> np.ndarray:
    prof = rings["profile"]
    f = (rr - rings["inner"]) / (rings["outer"] - rings["inner"])
    i = np.clip((f * (len(prof) - 1)).astype(np.int64), 0, len(prof) - 1)
    return prof[i].astype(np.float32) / 255.0


def _ring_alpha(rings: dict, rr: np.ndarray) -> np.ndarray:
    return _ring_rgba(rings, rr)[:, 3]


def ring_profile(png_path) -> np.ndarray | None:
    """Perfil radial RGBA (N, 4) do PNG dos anéis (média nas linhas)."""
    from PySide6.QtGui import QImage

    img = QImage(str(png_path))
    if img.isNull():
        return None
    img = img.convertToFormat(QImage.Format_RGBA8888)
    w, h = img.width(), img.height()
    arr = np.frombuffer(img.constBits(), np.uint8).reshape(h, img.bytesPerLine())
    arr = arr[:, : w * 4].reshape(h, w, 4).astype(np.float32)
    return arr.mean(axis=0).astype(np.uint8)
