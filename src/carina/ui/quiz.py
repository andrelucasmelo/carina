"""Quiz / modo aula (v0.22 T4) — Tours ▸ Quiz do céu.

Joga com o céu do momento no local do usuário. Ao abrir, o estado do céu é
fotografado (``SkyState``) e, ao fechar, restaurado — nomes escondidos e
destaques do jogo não ficam para trás.
"""

from __future__ import annotations

import random

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout)

from ..core import quiz as Q


class QuizDialog(QDialog):
    def __init__(self, main, parent=None, seed: int | None = None) -> None:
        super().__init__(parent or main)
        from ..core.skystate import SkyState

        self.main = main
        self.sky = main.sky
        self.setWindowTitle(self.tr("Quiz do céu"))
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.resize(420, 300)
        self.rng = random.Random(seed)
        self.score = Q.Score()
        self.question: Q.Question | None = None
        self.answered = False
        self.recent: list = []
        self.state = SkyState.capture(self.sky, main.engine)

        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItem(self.tr("Qual constelação é esta?"), "const")
        self.mode.addItem(self.tr("Encontre a estrela"), "star")
        self.mode.currentIndexChanged.connect(lambda *_: self.next_question())
        top.addWidget(self.mode, 1)
        self.lbl_score = QLabel()
        top.addWidget(self.lbl_score)
        lay.addLayout(top)
        self.prompt = QLabel()
        self.prompt.setWordWrap(True)
        self.prompt.setStyleSheet("font-size:14pt; font-weight:600;")
        lay.addWidget(self.prompt)
        grid = QGridLayout()
        self.buttons: list[QPushButton] = []
        for k in range(4):
            b = QPushButton()
            b.setMinimumHeight(34)
            b.clicked.connect(lambda _c=False, i=k: self._choose(i))
            grid.addWidget(b, k // 2, k % 2)
            self.buttons.append(b)
        lay.addLayout(grid)
        self.feedback = QLabel()
        self.feedback.setWordWrap(True)
        lay.addWidget(self.feedback)
        row = QHBoxLayout()
        self.btn_next = QPushButton(self.tr("Próxima ▶"))
        self.btn_next.clicked.connect(self.next_question)
        close = QPushButton(self.tr("Fechar"))
        close.clicked.connect(self.close)
        row.addStretch(1)
        row.addWidget(self.btn_next)
        row.addWidget(close)
        lay.addLayout(row)
        self.sky.selectionChanged.connect(self._sky_clicked)
        self.next_question()

    # ------------------------------------------------------------------
    def _when(self):
        return self.main.engine.time.current_datetime()

    def next_question(self) -> None:
        import numpy as np

        sky = self.sky
        sky.clear_highlights()
        self.answered = False
        self.feedback.setText("")
        mode = self.mode.currentData()
        when = self._when()
        if mode == "const":
            sky.set_layer("const_lines", True)
            sky.set_const_label_mode("none")
            cids = Q.visible_constellations(self.main.engine, sky.const_info, when)
            pool = list({c["id"] for c in sky.const_info if int(c.get("rank", 3)) <= 2})
            self.question = Q.const_question(cids, self.rng, pool, self.recent[-5:])
            for b in self.buttons:
                b.show()
            if self.question is None:
                self.prompt.setText(self.tr("Nenhuma constelação de destaque alta agora — "
                                            "tente à noite ou mude a hora."))
                return
            for b, (_key, label) in zip(self.buttons, self.question.options):
                b.setText(label)
                b.setEnabled(True)
            self.prompt.setText(self.tr("Qual é a constelação acesa no céu?"))
            k = next(i for i, c in enumerate(sky.const_info) if c["id"] == self.question.answer)
            m = self.main.engine.horizontal_matrix(self.main.engine.ts.from_datetime(when))
            sky.fly_to(np.asarray(m, float) @ sky.const_centers[k].astype(float), 75.0, 700)
            sky.highlight_constellation(self.question.answer, 3600)
        else:
            for b in self.buttons:
                b.hide()
            sky.set_layer("star_names", False)
            idxs = Q.visible_bright_stars(self.main.engine, self.main.star_catalog, when)
            self.question = Q.star_question(idxs, self.main.star_catalog, self.rng,
                                            self.recent[-5:])
            if self.question is None:
                self.prompt.setText(self.tr("Nenhuma estrela brilhante alta agora."))
                return
            sky.selection = None
            self.prompt.setText(self.tr("Clique em {s} no céu.").format(s=self.question.label))
        self.recent.append(self.question.answer)
        self._update_score()

    def _choose(self, k: int) -> None:
        if self.question is None or self.answered or self.question.kind != "const":
            return
        key = self.question.options[k][0]
        self._answer(self.question.check(key))

    def _sky_clicked(self, selection) -> None:
        q = self.question
        if q is None or self.answered or q.kind != "star" or selection is None:
            return
        self.answer_star(selection)

    def answer_star(self, selection) -> bool:
        q = self.question
        ok = selection == ("star", q.answer)
        self._answer(ok)
        if not ok:
            self.sky.goto_object(("star", q.answer))
        return ok

    def _answer(self, ok: bool) -> None:
        self.answered = True
        self.score.add(ok)
        q = self.question
        if ok:
            self.feedback.setText(self.tr("✓ Isso mesmo: {n}!").format(n=q.label))
            self.feedback.setStyleSheet("color:#7fd19b; font-size:11pt;")
        else:
            self.feedback.setText(self.tr("✗ Era {n}.").format(n=q.label))
            self.feedback.setStyleSheet("color:#f3a0a0; font-size:11pt;")
        for b in self.buttons:
            b.setEnabled(False)
        self._update_score()

    def _update_score(self) -> None:
        self.lbl_score.setText(self.tr("Acertos: {s}").format(s=self.score.text()))

    def closeEvent(self, e) -> None:
        try:
            self.sky.selectionChanged.disconnect(self._sky_clicked)
        except (RuntimeError, TypeError):
            pass
        self.state.restore(self.sky, self.main.engine)
        super().closeEvent(e)
