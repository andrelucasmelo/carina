"""Assistente de primeiro uso (v0.16 T6).

Três passos na primeira abertura: **onde você está** (cidade), **como é o
seu céu** (Bortle, com sugestão pela população da cidade) e **com o que
você observa** (instrumento da nota da noite), com a opção de desenhar o
horizonte do quintal e abrir o "Hoje à noite" ao terminar.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout,
    QWizard, QWizardPage,
)

from ..config import ObserverLocation
from .preferences_dialog import INSTRUMENTS

BORTLE_TEXT = {
    1: "Céu excelente — sertão, alta montanha", 2: "Céu muito escuro — rural remoto",
    3: "Céu rural", 4: "Transição rural/subúrbio", 5: "Subúrbio",
    6: "Subúrbio claro", 7: "Periferia urbana", 8: "Cidade", 9: "Centro de grande cidade",
}


def suggest_bortle(population: int | None) -> int:
    """Sugestão de Bortle pela população da cidade (regra prática)."""
    pop = population or 0
    if pop >= 1_000_000:
        return 8
    if pop >= 200_000:
        return 7
    if pop >= 50_000:
        return 6
    if pop >= 10_000:
        return 5
    return 4


def city_location(city: dict) -> ObserverLocation:
    return ObserverLocation(name=f"{city['n']}, {city['c']}", latitude=city["lat"],
                            longitude=city["lon"], elevation=float(city.get("el") or 0),
                            timezone=city.get("tz", ""))


class FirstRunWizard(QWizard):
    """Bem-vindo ao Carina: cidade, céu e instrumento."""

    def __init__(self, current: ObserverLocation, bortle: int = 5,
                 instrument: str = "pequeno", parent=None) -> None:
        super().__init__(parent)
        from .location_dialog import load_cities

        self.setWindowTitle(self.tr("Bem-vindo ao Carina"))
        self.setWizardStyle(QWizard.ModernStyle)
        self.setButtonText(QWizard.NextButton, self.tr("Avançar >"))
        self.setButtonText(QWizard.BackButton, self.tr("< Voltar"))
        self.setButtonText(QWizard.FinishButton, self.tr("Começar"))
        self.setButtonText(QWizard.CancelButton, self.tr("Pular"))
        self.resize(640, 520)
        self.cities = load_cities()
        self.chosen = None
        self.current = current

        # --- 1. cidade -------------------------------------------------------
        p1 = QWizardPage()
        p1.setTitle(self.tr("Onde você observa?"))
        p1.setSubTitle(self.tr("Todos os horários passam a ser os do fuso da cidade."))
        self.search = QLineEdit()
        self.search.setPlaceholderText(self.tr("Digite o nome da cidade…"))
        self.list = QListWidget()
        self.picked = QLabel()
        l1 = QVBoxLayout(p1)
        l1.addWidget(self.search)
        l1.addWidget(self.list, 1)
        l1.addWidget(self.picked)
        self.search.textChanged.connect(self._filter)
        self.list.currentItemChanged.connect(self._pick)

        # --- 2. céu ------------------------------------------------------------
        p2 = QWizardPage()
        p2.setTitle(self.tr("Como é o seu céu?"))
        p2.setSubTitle(self.tr("A escala de Bortle vai de 1 (céu perfeito) a 9 (centro "
                               "de cidade grande). Ela muda o céu desenhado e as notas."))
        self.bortle = QComboBox()
        for n, text in BORTLE_TEXT.items():
            self.bortle.addItem(f"{n} — {self.tr(text)}", n)
        self.bortle.setCurrentIndex(max(0, self.bortle.findData(bortle)))
        self.suggestion = QLabel()
        self.suggestion.setWordWrap(True)
        l2 = QVBoxLayout(p2)
        l2.addWidget(self.bortle)
        l2.addWidget(self.suggestion)
        l2.addStretch(1)

        # --- 3. instrumento ------------------------------------------------------
        p3 = QWizardPage()
        p3.setTitle(self.tr("Com o que você observa?"))
        p3.setSubTitle(self.tr("A nota de cada objeto diz se ele vale a pena com o seu "
                               "instrumento. Dá para mudar depois em Preferências."))
        self.instrument = QComboBox()
        for key, label in INSTRUMENTS:
            self.instrument.addItem(self.tr(label), key)
        self.instrument.setCurrentIndex(max(0, self.instrument.findData(instrument)))
        self.want_horizon = QCheckBox(self.tr("Desenhar o horizonte do quintal (prédios, "
                                              "árvores) ao terminar"))
        self.want_tonight = QCheckBox(self.tr("Mostrar o que vale a pena esta noite"))
        self.want_tonight.setChecked(True)
        l3 = QVBoxLayout(p3)
        l3.addWidget(self.instrument)
        l3.addSpacing(12)
        l3.addWidget(self.want_horizon)
        l3.addWidget(self.want_tonight)
        l3.addStretch(1)
        for page in (p1, p2, p3):
            self.addPage(page)
        # só agora (com a página do céu pronta) a cidade atual é procurada,
        # para a sugestão de Bortle acompanhar a escolha
        self.search.setText(current.name.split(",")[0])
        if not self.list.count():
            self.search.clear()

    def _filter(self, text: str) -> None:
        t = text.strip().lower()
        self.list.clear()
        shown = 0
        for city in self.cities:
            label = f"{city['n']}, {city['c']}"
            if t and t not in label.lower():
                continue
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, city)
            self.list.addItem(item)
            shown += 1
            if shown >= 200:
                break
        if self.list.count():
            self.list.setCurrentRow(0)

    def _pick(self, item, _prev=None) -> None:
        if item is None:
            return
        self.chosen = item.data(Qt.UserRole)
        self.picked.setText(self.tr("Escolhida: {c} · fuso {tz}").format(
            c=item.text(), tz=self.chosen.get("tz", "—")))
        sug = suggest_bortle(self.chosen.get("pop"))
        self.suggestion.setText(self.tr(
            "Sugestão para {c} ({p} habitantes): Bortle {b}. Se você observa fora da "
            "cidade, escolha um número menor.").format(
                c=self.chosen["n"], p=f"{int(self.chosen.get('pop') or 0):,}".replace(",", "."),
                b=sug))
        self.bortle.setCurrentIndex(max(0, self.bortle.findData(sug)))

    def result_values(self) -> dict:
        loc = city_location(self.chosen) if self.chosen else self.current
        return {"location": loc, "bortle": int(self.bortle.currentData()),
                "instrument": self.instrument.currentData(),
                "horizon": self.want_horizon.isChecked(),
                "tonight": self.want_tonight.isChecked()}
