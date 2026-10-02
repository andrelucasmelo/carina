"""Anticolisão dos rótulos das cartas de localização (D12)."""

from PySide6.QtCore import QRectF
from PySide6.QtGui import QFont, QImage, QPainter

from carina.ui.finderchart import _draw_label_avoiding


def test_label_moves_to_a_free_candidate(qt_app):
    img = QImage(300, 200, QImage.Format_RGB32)
    img.fill(0xFFFFFFFF)
    p = QPainter(img)
    p.setFont(QFont("Segoe UI", 9))
    taken = [QRectF(95, 85, 60, 20)]          # ocupa o primeiro candidato
    _draw_label_avoiding(p, "Deneb", taken, [(100, 100), (100, 150)])
    p.end()
    assert len(taken) == 2
    assert taken[1].top() > 120                # foi para o segundo candidato


def test_label_falls_back_to_first_when_all_collide(qt_app):
    img = QImage(300, 200, QImage.Format_RGB32)
    p = QPainter(img)
    p.setFont(QFont("Segoe UI", 9))
    taken = [QRectF(0, 0, 300, 200)]
    _draw_label_avoiding(p, "Sadr", taken, [(10, 20), (10, 60)])
    p.end()
    assert len(taken) == 2 and taken[1].top() < 30
