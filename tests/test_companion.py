"""QR code e servidor do companheiro no celular (v0.19 T5)."""

import json
import urllib.error
import urllib.request

import pytest


def test_reed_solomon_reference():
    """Exemplo clássico "HELLO WORLD" 1-M (thonky.com): 10 codewords de EC."""
    from carina.core.qr import rs_encode, rs_syndromes

    data = [32, 91, 11, 120, 209, 114, 220, 77, 67, 64, 236, 17, 236, 17, 236, 17]
    ec = rs_encode(data, 10)
    assert ec == [196, 35, 39, 119, 235, 215, 231, 226, 93, 23]
    assert not any(rs_syndromes(data + ec, 10))


def test_format_bits_reference():
    from carina.core.qr import format_bits

    assert format_bits("M", 0) == 0b101010000010010
    assert format_bits("L", 0) == 0b111011111000100
    assert format_bits("L", 4) == 0b110011000101111


@pytest.mark.parametrize("text,level", [
    ("http://192.168.0.10:8765/?t=abc123", "M"),
    ("Carina", "L"),
    ("http://10.0.0.2:8765/?t=" + "x" * 50, "L"),
])
def test_qr_roundtrip(text, level):
    from carina.core.qr import decode, encode

    m = encode(text, level)
    n = len(m)
    assert n in (21, 25, 29, 33, 37) and all(len(r) == n for r in m)
    # padrões de localização nos três cantos
    for r0, c0 in ((0, 0), (0, n - 7), (n - 7, 0)):
        assert m[r0][c0] == 1 and m[r0 + 3][c0 + 3] == 1 and m[r0 + 1][c0 + 1] == 0
    assert decode(m) == text


def test_server_plan_and_observed():
    from carina.core.companion_server import CompanionServer

    received = []
    plan = {"title": "Teste", "items": [{"name": "M 42", "kind": "dso", "ident": "M 42",
                                         "time": "21:00", "observed": False}]}
    srv = CompanionServer(lambda: plan, lambda kind, ident, name: received.append((kind, ident, name)),
                          port=0, host="127.0.0.1")
    srv.start()
    try:
        base = f"http://127.0.0.1:{srv.port}"
        with urllib.request.urlopen(f"{base}/api/plan?t={srv.token}", timeout=5) as r:
            got = json.loads(r.read().decode("utf-8"))
        assert got["items"][0]["name"] == "M 42"
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(f"{base}/api/plan?t=errado", timeout=5)
        assert err.value.code == 403
        req = urllib.request.Request(
            f"{base}/api/observed?t={srv.token}", method="POST",
            data=json.dumps({"kind": "dso", "ident": "M 42", "name": "M 42"}).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            assert json.loads(r.read().decode("utf-8"))["ok"]
        assert received == [("dso", "M 42", "M 42")]
        with urllib.request.urlopen(f"{base}/?t={srv.token}", timeout=5) as r:
            page = r.read().decode("utf-8")
        assert "<html" in page.lower() and srv.token in page
    finally:
        srv.stop()


def test_dialog_end_to_end(isolated_userdata):
    """Diálogo liga o servidor, o 'celular' marca observado e o registro
    chega ao diário pela fila da interface."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from carina.ui.companion_dialog import CompanionDialog

    plan = {"title": "T", "items": [{"name": "M 8", "kind": "dso", "ident": "M 8"}]}
    got = []
    dlg = CompanionDialog(lambda: plan)
    dlg.observedReceived.connect(lambda k, i, n: got.append((k, i, n)), Qt.QueuedConnection)
    dlg.start(port=0)
    try:
        assert dlg.server.running and dlg.qr.matrix is not None
        base = f"http://127.0.0.1:{dlg.server.port}"
        with urllib.request.urlopen(f"{base}/api/plan?t={dlg.server.token}", timeout=5) as r:
            assert json.loads(r.read().decode("utf-8"))["items"][0]["name"] == "M 8"
        req = urllib.request.Request(f"{base}/api/observed?t={dlg.server.token}", method="POST",
                                     data=b'{"kind":"dso","ident":"M 8","name":"M 8"}')
        urllib.request.urlopen(req, timeout=5).read()
        for _ in range(20):
            QApplication.processEvents()
        assert got == [("dso", "M 8", "M 8")]
    finally:
        dlg.stop()
        dlg.close()
