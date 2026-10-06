"""Quiz / modo aula (v0.22 T4): perguntas a partir do céu do momento.

- **Qual constelação é esta?** — uma constelação de destaque acima de 25°
  é acesa no céu (sem o nome) e há quatro opções;
- **Encontre a estrela** — uma estrela brilhante acima de 20° é pedida pelo
  nome; o usuário clica nela no céu (os nomes ficam escondidos).

Sem Qt: a interface (``ui/quiz.py``) só desenha e repassa as respostas.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import numpy as np


@dataclass
class Question:
    kind: str                       # "const" | "star"
    answer: object                  # sigla da constelação | índice da estrela
    label: str                      # nome da resposta
    options: list = field(default_factory=list)   # [(chave, rótulo)] — só "const"

    def check(self, choice) -> bool:
        return choice == self.answer


@dataclass
class Score:
    right: int = 0
    wrong: int = 0

    def add(self, ok: bool) -> None:
        if ok:
            self.right += 1
        else:
            self.wrong += 1

    @property
    def total(self) -> int:
        return self.right + self.wrong

    def text(self) -> str:
        return f"{self.right} de {self.total}" if self.total else "—"


def _altitudes(engine, icrs: np.ndarray, when) -> np.ndarray:
    m = np.asarray(engine.horizontal_matrix(engine.ts.from_datetime(when)), np.float64)
    v = icrs @ m.T
    return np.degrees(np.arcsin(np.clip(v[:, 2], -1.0, 1.0)))


def visible_constellations(engine, const_info: list[dict], when, min_alt: float = 25.0,
                           max_rank: int = 2) -> list[str]:
    seen, cids, vecs = set(), [], []
    for c in const_info:
        if c["id"] in seen or int(c.get("rank", 3)) > max_rank:
            continue
        seen.add(c["id"])
        ra, dec = math.radians(c["ra"]), math.radians(c["dec"])
        cids.append(c["id"])
        vecs.append([math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra), math.sin(dec)])
    if not cids:
        return []
    alts = _altitudes(engine, np.array(vecs), when)
    return [c for c, a in zip(cids, alts) if a >= min_alt]


def visible_bright_stars(engine, stars, when, min_alt: float = 20.0,
                         mag: float = 2.0) -> list[int]:
    n = stars.count_brighter_than(mag)
    idx = [i for i in range(n) if stars.proper.get(i)]
    if not idx:
        return []
    alts = _altitudes(engine, np.asarray(stars.xyz[idx], np.float64), when)
    return [i for i, a in zip(idx, alts) if a >= min_alt]


def const_question(cids: list[str], rng: random.Random, pool: list[str] | None = None,
                   recent: list | None = None) -> Question | None:
    """Pergunta sobre uma constelação visível; distratores do mesmo céu (ou de
    ``pool`` quando o céu tem poucas)."""
    from ..catalogs.constnames import CONSTELLATIONS

    choices = [c for c in cids if c not in (recent or [])] or list(cids)
    if not choices:
        return None
    answer = rng.choice(choices)
    others = [c for c in (cids if len(cids) >= 4 else (pool or cids)) if c != answer]
    distract = rng.sample(others, min(3, len(others)))
    opts = [answer] + distract
    rng.shuffle(opts)
    name = lambda c: CONSTELLATIONS.get(c, (c, c))[1]  # noqa: E731
    return Question("const", answer, name(answer), [(c, name(c)) for c in opts])


def star_question(idxs: list[int], stars, rng: random.Random,
                  recent: list | None = None) -> Question | None:
    choices = [i for i in idxs if i not in (recent or [])] or list(idxs)
    if not choices:
        return None
    i = rng.choice(choices)
    return Question("star", int(i), stars.proper.get(int(i), f"HIP {int(stars.hip[i])}"))
