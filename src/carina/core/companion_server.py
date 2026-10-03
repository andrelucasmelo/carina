"""Companheiro no celular: servidor HTTP local (v0.19 T5, ADR-049).

O celular, na mesma rede Wi-Fi, abre a página do Carina pelo QR code:
roteiro da noite em vermelho (para não perder a adaptação ao escuro),
checklist e o botão **observado**, que vai para o diário do computador.

Segurança e privacidade:

- só responde na rede local (o endereço é o IP da máquina na LAN);
- cada vez que o companheiro é ligado nasce um **código de acesso**
  aleatório na URL — sem ele, nada é servido (403);
- nada sai da rede: o servidor não acessa a internet, e a página não
  carrega nada de fora (CSS e JS embutidos).

Usa só a biblioteca padrão (``http.server`` numa thread).
"""

from __future__ import annotations

import json
import secrets
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

DEFAULT_PORT = 8765


def local_ip() -> str:
    """IP da máquina na rede local (sem enviar pacotes: conectar um
    socket UDP só escolhe a interface de saída)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


class CompanionServer:
    """Servidor do companheiro. ``plan_provider()`` devolve o roteiro em
    dicionário; ``on_observed(kind, ident, name)`` registra no diário
    (chamado na thread do servidor — quem recebe deve repassar à
    interface com segurança)."""

    def __init__(self, plan_provider, on_observed, port: int = DEFAULT_PORT,
                 host: str = "0.0.0.0") -> None:
        self.plan_provider = plan_provider
        self.on_observed = on_observed
        self.token = secrets.token_urlsafe(8)
        self.host = host
        self.requested_port = port
        self.port = port
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.last_seen: str | None = None

    # -- ciclo de vida ------------------------------------------------------
    def start(self) -> None:
        handler = self._make_handler()
        tries = [self.requested_port] if self.requested_port == 0 else \
            [self.requested_port + k for k in range(10)]
        last_err = None
        for port in tries:
            try:
                self._httpd = ThreadingHTTPServer((self.host, port), handler)
                break
            except OSError as exc:            # porta ocupada: tenta a próxima
                last_err = exc
        if self._httpd is None:
            raise last_err
        self._httpd.daemon_threads = True
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever,
                                        name="carina-companion", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None

    @property
    def running(self) -> bool:
        return self._httpd is not None

    def url(self, ip: str | None = None) -> str:
        return f"http://{ip or local_ip()}:{self.port}/?t={self.token}"

    # -- HTTP -------------------------------------------------------------------
    def _make_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_a):          # silencioso
                pass

            def _auth(self) -> bool:
                q = parse_qs(urlparse(self.path).query)
                ok = q.get("t", [""])[0] == server.token
                if not ok:
                    self._send(403, "text/plain; charset=utf-8", "Código de acesso inválido.")
                else:
                    server.last_seen = self.client_address[0]
                return ok

            def _send(self, code: int, ctype: str, body) -> None:
                data = body.encode("utf-8") if isinstance(body, str) else body
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                path = urlparse(self.path).path
                if not self._auth():
                    return
                if path == "/api/plan":
                    try:
                        plan = server.plan_provider() or {}
                    except Exception as exc:     # nunca derruba o servidor
                        plan = {"title": "Erro", "items": [], "error": str(exc)}
                    self._send(200, "application/json; charset=utf-8",
                               json.dumps(plan, ensure_ascii=False, default=str))
                elif path in ("/", "/index.html"):
                    self._send(200, "text/html; charset=utf-8",
                               PAGE.replace("__TOKEN__", server.token))
                else:
                    self._send(404, "text/plain; charset=utf-8", "não encontrado")

            def do_POST(self):
                path = urlparse(self.path).path
                if not self._auth():
                    return
                if path != "/api/observed":
                    self._send(404, "text/plain; charset=utf-8", "não encontrado")
                    return
                length = int(self.headers.get("Content-Length", "0") or 0)
                try:
                    body = json.loads(self.rfile.read(min(length, 10000)).decode("utf-8"))
                    server.on_observed(str(body["kind"]), str(body["ident"]),
                                       str(body.get("name", body["ident"])))
                    self._send(200, "application/json", json.dumps({"ok": True}))
                except Exception as exc:
                    self._send(400, "application/json",
                               json.dumps({"ok": False, "error": str(exc)}))

        return Handler


PAGE = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Carina — companheiro</title>
<style>
 :root { color-scheme: dark; }
 body { margin:0; background:#000; color:#c33; font:16px/1.4 system-ui, sans-serif; }
 header { padding:14px 16px; border-bottom:1px solid #300; }
 h1 { font-size:18px; margin:0; color:#e44; }
 #sub { font-size:13px; color:#922; margin-top:4px; }
 ul { list-style:none; margin:0; padding:0; }
 li { padding:12px 16px; border-bottom:1px solid #200; display:flex; gap:12px; align-items:center; }
 .t { font-variant-numeric:tabular-nums; color:#a22; min-width:48px; }
 .n { flex:1; }
 .n b { color:#e44; font-weight:600; }
 .n small { display:block; color:#822; font-size:13px; }
 button { background:#100; color:#c33; border:1px solid #600; border-radius:8px;
          padding:10px 12px; font-size:15px; }
 li.done { opacity:.45; } li.done button { border-color:#300; }
 #err { padding:16px; color:#e55; }
 footer { padding:16px; font-size:12px; color:#611; }
</style></head><body>
<header><h1 id="title">Carina</h1><div id="sub">carregando…</div></header>
<div id="err"></div><ul id="list"></ul>
<footer>Tela em vermelho para preservar a visão noturna. Abaixe o brilho do celular.</footer>
<script>
const T = "__TOKEN__";
const done = new Set(JSON.parse(localStorage.getItem("carina-done-" + T) || "[]"));
function esc(s){ return String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }
async function load(){
  try {
    const r = await fetch("/api/plan?t=" + T, {cache:"no-store"});
    const p = await r.json();
    document.getElementById("title").textContent = p.title || "Carina";
    document.getElementById("sub").textContent = p.subtitle || "";
    const ul = document.getElementById("list"); ul.innerHTML = "";
    (p.items || []).forEach(it => {
      const key = it.kind + ":" + it.ident;
      const li = document.createElement("li");
      if (it.observed || done.has(key)) li.className = "done";
      li.innerHTML = `<span class="t">${esc(it.time)}</span>
        <span class="n"><b>${esc(it.name)}</b><small>${esc(it.detail)}</small></span>
        <button>${li.className ? "✓" : "observado"}</button>`;
      li.querySelector("button").onclick = async () => {
        await fetch("/api/observed?t=" + T, {method:"POST", headers:{"Content-Type":"application/json"},
          body: JSON.stringify({kind: it.kind, ident: it.ident, name: it.name})});
        done.add(key); localStorage.setItem("carina-done-" + T, JSON.stringify([...done]));
        li.className = "done"; li.querySelector("button").textContent = "✓";
      };
      ul.appendChild(li);
    });
    document.getElementById("err").textContent = "";
  } catch (e) {
    document.getElementById("err").textContent = "Sem conexão com o Carina. O computador está ligado e na mesma rede?";
  }
}
load(); setInterval(load, 60000);
</script></body></html>
"""
