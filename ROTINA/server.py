"""
ROTINA // servidor local
------------------------
Serve o site (index.html) e uma API REST que o site E o Jarvis usam.
Só usa a biblioteca padrão do Python (nada pra instalar).

    python server.py            -> http://localhost:8765
    python server.py --port 9000

Dados ficam em data.json, na mesma pasta.
Senha: pedida na 1ª vez (troque com: python server.py --set-password).
O Jarvis entra com a chave ROTINA_KEY (acesso total, sem confirmação).
Só escuta em 127.0.0.1: de fora, só pelo túnel (abrir_faculdade.bat) + senha.
"""
import getpass
import hashlib
import hmac
import json
import os
import secrets
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE, "data.json")
PORT = 8765
LOCK = threading.Lock()
CONFIG_FILE = os.path.join(BASE, "config.json")
INDEX_FILE = os.path.join(BASE, "index.html")
if not os.path.exists(INDEX_FILE):
    INDEX_FILE = os.path.join(BASE, "index (1).html")

# ---------- segurança ----------
SESSIONS = {}            # token -> expira_em (em memória; reiniciar = todos deslogam)
FAILS = {}               # ip -> [tentativas, bloqueado_ate]
LOCAL_SESSION_H = 24 * 30   # no seu PC: 30 dias
REMOTE_SESSION_H = 4        # vindo do link (faculdade): 4 horas


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def hash_pw(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex()


def set_password():
    cfg = load_config()
    while True:
        a = getpass.getpass("Nova senha do ROTINA (mín. 8 caracteres; NÃO aparece ao digitar, é normal): ")
        if len(a) < 8:
            print("Muito curta."); continue
        if getpass.getpass("Repita: ") != a:
            print("Não bate."); continue
        break
    cfg["salt"] = secrets.token_hex(16)
    cfg["hash"] = hash_pw(a, cfg["salt"])
    cfg.setdefault("jarvis_key", secrets.token_urlsafe(32))
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    print("\nSenha salva.")
    print("A chave do Jarvis foi salva em config.json; copie-a localmente para o .env sem publicá-la.")


CFG = {}


LOGIN_HTML = """<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>ROTINA // login</title>
<link href="https://fonts.googleapis.com/css2?family=Anton&family=Rubik+Wet+Paint&family=Space+Mono&display=swap" rel="stylesheet">
<style>body{background:#000;color:#fff;font-family:'Space Mono',monospace;min-height:100vh;display:grid;place-items:center;margin:0;padding:16px}
form{border:3px solid #fff;padding:28px;width:100%;max-width:360px;display:flex;flex-direction:column;gap:14px}
h1{font-family:'Rubik Wet Paint';font-size:64px;margin:0;transform:rotate(-2deg);line-height:.9}
input{background:#000;color:#fff;border:2px solid #fff;padding:12px;font:inherit}
button{background:#fff;color:#000;border:2px solid #fff;font-family:Anton;letter-spacing:3px;font-size:20px;padding:10px;cursor:pointer}
button:hover{background:#000;color:#fff}.e{color:#8a8a8a;font-size:13px;min-height:1em}</style></head>
<body><form method="post" action="/login"><h1>roTiNa</h1>
<input type="password" name="pw" placeholder="senha" autofocus required autocomplete="current-password">
<button>entrar</button><div class="e">%ERR%</div></form></body></html>"""

SETUP_HTML = LOGIN_HTML.replace('<input type="password" name="pw" placeholder="senha" autofocus required autocomplete="current-password">',
  '<div style="color:#8a8a8a;font-size:13px">Primeiro acesso: crie sua senha (mín. 8 caracteres)</div>'
  '<input type="password" name="pw" placeholder="nova senha" autofocus required minlength="8" autocomplete="new-password">'
  '<input type="password" name="pw2" placeholder="repita a senha" required minlength="8" autocomplete="new-password">'
  ).replace('<form method="post" action="/login">', '<form method="post" action="/setup">').replace(">entrar<", ">criar senha<")

DONE_HTML = """<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ROTINA // pronto</title><style>body{background:#0a0a0b;color:#fff;font-family:system-ui;display:grid;place-items:center;min-height:100vh;margin:0;padding:16px}
div{max-width:560px;border:1px solid #333;border-radius:14px;padding:26px;background:#131315}h1{margin:0 0 10px;font-size:22px}
code{display:block;background:#000;border:1px solid #ff7a1a;border-radius:8px;padding:12px;margin:10px 0;word-break:break-all;color:#ff7a1a;user-select:all}
a{display:inline-block;margin-top:12px;background:#ff7a1a;color:#111;padding:10px 16px;border-radius:10px;text-decoration:none;font-weight:700}p{color:#aaa;font-size:14px;line-height:1.5}</style></head>
<body><div><h1>Senha criada ✓</h1><p>Chave do Jarvis: copie a linha abaixo e cole no arquivo <b>.env</b> do Jarvis (ela também fica salva no config.json):</p>
<code>ROTINA_KEY=%KEY%</code><a href="/">entrar no ROTINA</a></div></body></html>"""

# Coleções que o site e o Jarvis podem mexer
COLLECTIONS = ["tasks", "ideas", "transactions", "businesses", "bizEntries", "investments"]


def empty_state():
    now = time.strftime("%Y-%m-%d")
    biz = [
        {"id": uuid.uuid4().hex[:8], "name": n, "status": "ativo", "color": c, "created": now}
        for n, c in [("Capital Tech Pro", "#ffffff"), ("UniGo", "#d9d9d9"),
                     ("UniMove", "#a6a6a6"), ("EULER", "#737373")]
    ]
    s = {c: [] for c in COLLECTIONS}
    s["businesses"] = biz
    s["log"] = []
    s["rev"] = 0
    return s


def load():
    if not os.path.exists(DATA_FILE):
        save(empty_state())
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        s = json.load(f)
    for c in COLLECTIONS + ["log"]:
        s.setdefault(c, [])
    s.setdefault("rev", 0)
    s.setdefault("bankAccounts", [])
    s.setdefault("pluggyIgnored", [])
    return s


def save(s):
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)


def log(s, source, action, col, item):
    label = item.get("title") or item.get("name") or item.get("text") or item.get("desc") or item.get("id")
    s["log"].insert(0, {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "source": source,
                        "action": action, "col": col, "label": str(label)[:80]})
    s["log"] = s["log"][:300]


# ---------- métricas (o Jarvis pode pedir /api/summary) ----------
def biz_metrics(s, biz_id):
    e = [x for x in s["bizEntries"] if x.get("bizId") == biz_id]
    tot = lambda t: sum(float(x.get("amount", 0)) for x in e if x.get("type") == t)
    rev, cost, inv, wd = tot("revenue"), tot("cost"), tot("invest"), tot("withdraw")
    profit = rev - cost
    return {
        "receita": rev, "custos": cost, "investido": inv, "retirado": wd,
        "lucro": profit,
        "margem_pct": (profit / rev * 100) if rev else 0,
        "roi_pct": (profit / inv * 100) if inv else 0,
        "caixa": inv + rev - cost - wd,
    }


def summary(s):
    today = time.strftime("%Y-%m-%d")
    tx = s["transactions"]
    entrada = sum(float(x["amount"]) for x in tx if x.get("type") == "in")
    saida = sum(float(x["amount"]) for x in tx if x.get("type") == "out")
    negocios = []
    for b in s["businesses"]:
        m = biz_metrics(s, b["id"]); m["nome"] = b["name"]; m["id"] = b["id"]; m["status"] = b.get("status")
        negocios.append(m)
    inv_tot = sum(float(x.get("invested", 0)) for x in s["investments"])
    inv_cur = sum(float(x.get("current", x.get("invested", 0))) for x in s["investments"])
    tasks_today = [t for t in s["tasks"] if t.get("date") == today or t.get("recur") in ("daily",)
                   or (t.get("recur") == "weekly" and int(t.get("weekday", -1)) == int(time.strftime("%w")))]
    done = [t for t in tasks_today if today in (t.get("doneDates") or [])]
    return {
        "data": today,
        "rotina": {"tarefas_hoje": len(tasks_today), "concluidas": len(done),
                   "pendentes": [t["title"] for t in tasks_today if t not in done]},
        "dinheiro": {"entradas": entrada, "saidas": saida, "saldo": entrada - saida},
        "negocios": negocios,
        "negocios_total": {
            "lucro": sum(n["lucro"] for n in negocios),
            "receita": sum(n["receita"] for n in negocios),
            "custos": sum(n["custos"] for n in negocios),
            "investido": sum(n["investido"] for n in negocios),
        },
        "investimentos": {"aplicado": inv_tot, "atual": inv_cur, "retorno": inv_cur - inv_tot,
                          "retorno_pct": ((inv_cur - inv_tot) / inv_tot * 100) if inv_tot else 0},
        "ideias": len(s["ideas"]),
    }


def _local_datetime(value, tz):
    """Interpreta datas do schema legado no timezone local, sem comparar strings."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed.astimezone(tz)


def _metrics_for_period(s, start, end):
    tz = start.tzinfo

    def in_period(item):
        stamp = _local_datetime(item.get("date") or item.get("created"), tz)
        return stamp is not None and start <= stamp < end

    transactions = [item for item in s.get("transactions", []) if in_period(item)]
    income = sum(float(item.get("amount", 0)) for item in transactions if item.get("type") == "in")
    expenses = sum(float(item.get("amount", 0)) for item in transactions if item.get("type") == "out")

    business_entries = [item for item in s.get("bizEntries", []) if in_period(item)]
    revenue = sum(float(item.get("amount", 0)) for item in business_entries if item.get("type") == "revenue")
    cost = sum(float(item.get("amount", 0)) for item in business_entries if item.get("type") == "cost")

    # Recorrências sem instâncias datadas não são estimadas: só tarefas cuja
    # data identifica o período entram no percentual.
    tasks = [item for item in s.get("tasks", []) if _local_datetime(item.get("date"), tz) is not None and in_period(item)]
    completed = 0
    for task in tasks:
        done_dates = [_local_datetime(value, tz) for value in (task.get("doneDates") or [])]
        if any(done is not None and start <= done < end for done in done_dates):
            completed += 1
    total = len(tasks)
    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "records": {"transactions": len(transactions), "business_entries": len(business_entries), "tasks": total},
        "personal_finance": {"income": income, "expenses": expenses, "net": income - expenses},
        "business": {"revenue": revenue, "cost": cost, "profit": revenue - cost},
        "productivity": {
            "tasks": total, "completed": completed, "pending": total - completed,
            "completion_pct": (completed / total * 100) if total else 0,
        },
    }


def weekly_summary(s, now=None):
    """Semana local atual (segunda 00:00 até agora) e semana anterior fechada."""
    now = now or datetime.now().astimezone()
    if now.tzinfo is None:
        now = now.astimezone()
    current_start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=now.weekday())
    previous_start = current_start - timedelta(days=7)
    current = _metrics_for_period(s, current_start, now + timedelta(microseconds=1))
    previous = _metrics_for_period(s, previous_start, current_start)
    current["period"]["end"] = now.isoformat()
    previous["period"]["end"] = (current_start - timedelta(microseconds=1)).isoformat()
    current["previous_week"] = previous
    return current


# ---------- Meu Pluggy (bancos) ----------
def run_pluggy():
    import pluggy_sync
    with LOCK:
        s = load()
        ign = set(s.get("pluggyIgnored", []))
        s["transactions"] += [{"id": i} for i in ign]           # truque: marca como "já conhecido"
        res = pluggy_sync.sync(s, CFG, log)
        s["transactions"] = [t for t in s["transactions"] if len(t) > 1]  # remove os marcadores
        save(s)
    print(f"[pluggy] {res['last']}: {res['new']} novas" + (f" | erros: {res['errors']}" if res["errors"] else ""))
    return res


def pluggy_loop():
    mins = int(CFG.get("pluggy_every_min", 60))
    while True:
        try:
            if CFG.get("pluggy_items"):
                run_pluggy()
        except Exception as e:
            print("[pluggy] falhou:", e)
        time.sleep(mins * 60)


def setup_pluggy():
    cfg = load_config()
    print("\n== Configurar Meu Pluggy ==")
    print("Pegue no dashboard.pluggy.ai (sua aplicação):")
    cfg["pluggy_client_id"] = input("Client ID: ").strip()
    cfg["pluggy_client_secret"] = input("Client Secret (cole com botão direito ou Ctrl+V): ").strip()
    print("Item IDs: pode deixar vazio (Enter) e conectar os bancos pelo botão no site.")
    extra = [x.strip() for x in input("Item IDs (opcional): ").split(",") if x.strip()]
    cfg["pluggy_items"] = list(dict.fromkeys(cfg.get("pluggy_items", []) + extra))
    cfg.setdefault("pluggy_every_min", 60)
    cfg.setdefault("pluggy_days", 90)
    cfg.setdefault("pluggy_include_cards", False)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    print("\nTestando conexão...")
    try:
        import pluggy_sync
        pl = pluggy_sync.Pluggy(cfg["pluggy_client_id"], cfg["pluggy_client_secret"])
        pl._auth()
        print("  OK: Client ID e Secret aceitos pela Pluggy.")
        for it in cfg["pluggy_items"]:
            i = pl.item(it)
            accs = pl.accounts(it)
            print(f"  OK {(i.get('connector') or {}).get('name')} ({i.get('status')}): {len(accs)} conta(s)")
        print("Tudo certo. Abra o site > Finanças > '+ conectar banco'.")
    except Exception as e:
        print("  ERRO:", e, "\n  Confira Client ID/Secret e os Item IDs e rode --pluggy de novo.")


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json", headers=None):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if "json" in ctype or "html" in ctype else ""))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # --- quem está pedindo? ---
    def _remote(self):
        # O Cloudflare Tunnel sempre adiciona esse cabeçalho: = acesso vindo de fora
        return bool(self.headers.get("Cf-Connecting-Ip"))

    def _ip(self):
        return self.headers.get("Cf-Connecting-Ip") or self.client_address[0]

    def _cookie_token(self):
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "rt_session":
                return v
        return None

    def _authed(self):
        key = self.headers.get("X-Api-Key")
        if key and CFG.get("jarvis_key") and hmac.compare_digest(key, CFG["jarvis_key"]):
            return "jarvis"
        tok = self._cookie_token()
        if tok and SESSIONS.get(tok, 0) > time.time():
            return "site"
        return None

    def _login_page(self, err=""):
        return self._send(200, LOGIN_HTML.replace("%ERR%", err).encode("utf-8"), "text/html")

    def _do_login(self):
        ip = self._ip()
        tries, until = FAILS.get(ip, [0, 0])
        if until > time.time():
            return self._login_page(f"bloqueado. tente em {int((until - time.time()) / 60) + 1} min")
        n = int(self.headers.get("Content-Length") or 0)
        from urllib.parse import parse_qs
        pw = parse_qs(self.rfile.read(n).decode("utf-8")).get("pw", [""])[0]
        if hmac.compare_digest(hash_pw(pw, CFG["salt"]), CFG["hash"]):
            FAILS.pop(ip, None)
            tok = secrets.token_urlsafe(32)
            hours = REMOTE_SESSION_H if self._remote() else LOCAL_SESSION_H
            SESSIONS[tok] = time.time() + hours * 3600
            ck = f"rt_session={tok}; HttpOnly; SameSite=Strict; Path=/; Max-Age={hours * 3600}"
            if self._remote():
                ck += "; Secure"
            return self._send(303, b"", "text/html", {"Location": "/", "Set-Cookie": ck})
        tries += 1
        FAILS[ip] = [tries, time.time() + 300 if tries >= 5 else 0]
        print(f"[!] senha errada de {ip} ({tries}x)")
        return self._login_page("senha errada" + (" — bloqueado por 5 min" if tries >= 5 else ""))

    def _logout(self):
        tok = self._cookie_token()
        SESSIONS.pop(tok, None)
        return self._send(303, b"", "text/html",
                          {"Location": "/", "Set-Cookie": "rt_session=; Path=/; Max-Age=0"})

    def _do_setup(self):
        if CFG.get("hash") or self._remote():
            return self._send(303, b"", "text/html", {"Location": "/"})
        n = int(self.headers.get("Content-Length") or 0)
        from urllib.parse import parse_qs
        q = parse_qs(self.rfile.read(n).decode("utf-8"))
        a, b = q.get("pw", [""])[0], q.get("pw2", [""])[0]
        if len(a) < 8 or a != b:
            return self._send(200, SETUP_HTML.replace("%ERR%", "senhas não batem ou menos de 8 caracteres").encode(), "text/html")
        cfg = load_config()
        cfg["salt"] = secrets.token_hex(16)
        cfg["hash"] = hash_pw(a, cfg["salt"])
        cfg.setdefault("jarvis_key", secrets.token_urlsafe(32))
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        CFG.update(cfg)
        print("Senha criada pelo navegador; a chave do Jarvis foi exibida somente na resposta local.")
        return self._send(200, DONE_HTML.replace("%KEY%", cfg["jarvis_key"]).encode(), "text/html")

    def _gate(self):
        """True = liberado. Senão já respondeu (login ou 401)."""
        if not CFG.get("hash"):  # primeiro acesso: só pelo próprio PC
            if self._remote():
                self._send(403, b"Configure a senha no PC primeiro.", "text/plain")
            elif self._parts()[0] == "api" and not self._authed():
                self._send(401, {"erro": "crie a senha primeiro"})
            elif not self._authed():
                self._send(200, SETUP_HTML.replace("%ERR%", "").encode(), "text/html")
            else:
                return True
            return False
        if self._authed():
            return True
        if self._parts()[0] == "api":
            self._send(401, {"erro": "não autenticado"})
        else:
            self._login_page()
        return False

    def log_message(self, *a):  # silencia o log padrão no terminal
        pass

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def _parts(self):
        p = urlparse(self.path).path.strip("/").split("/")
        return p

    def _source(self):
        return self._authed() or "?"

    def do_GET(self):
        p = self._parts()
        if p == ["api", "health"]:
            return self._send(200, {"status": "ok", "service": "ROTINA"})
        if p == ["logout"]:
            return self._logout()
        if not self._gate():
            return
        if p in ([""], ["index.html"]):
            with open(INDEX_FILE, "rb") as f:
                return self._send(200, f.read(), "text/html")
        if len(p) == 2 and p[0] == "img":  # imagens do painel (só nomes simples, sem ../)
            name = os.path.basename(p[1])
            fp = os.path.join(BASE, "img", name)
            ext = name.rsplit(".", 1)[-1].lower()
            if os.path.isfile(fp) and ext in ("jpg", "jpeg", "png", "webp", "gif"):
                with open(fp, "rb") as f:
                    return self._send(200, f.read(), "image/" + ("jpeg" if ext == "jpg" else ext))
            return self._send(404, {"erro": "imagem não encontrada"})
        if p[0] != "api":
            return self._send(404, {"erro": "não encontrado"})
        with LOCK:
            s = load()
        if len(p) == 2 and p[1] == "state":
            return self._send(200, s)
        if len(p) == 2 and p[1] == "rev":
            return self._send(200, {"rev": s["rev"]})
        if len(p) == 2 and p[1] == "summary":
            query = parse_qs(urlparse(self.path).query)
            return self._send(200, weekly_summary(s) if query.get("period") == ["week"] else summary(s))
        if len(p) == 2 and p[1] in COLLECTIONS:
            return self._send(200, s[p[1]])
        if len(p) == 3 and p[1] == "businesses" and p[2]:
            b = next((x for x in s["businesses"] if x["id"] == p[2] or x["name"].lower() == p[2].lower()), None)
            if not b:
                return self._send(404, {"erro": "negócio não encontrado"})
            return self._send(200, {**b, "metricas": biz_metrics(s, b["id"])})
        return self._send(404, {"erro": "rota inválida"})

    def do_POST(self):
        p = self._parts()
        if p == ["setup"]:
            return self._do_setup()
        if p == ["login"]:
            if not CFG.get("hash"):
                return self._send(303, b"", "text/html", {"Location": "/"})
            return self._do_login()
        if not self._gate():
            return
        if len(p) == 2 and p[0] == "api" and p[1] in COLLECTIONS:
            item = self._body()
            item.setdefault("id", uuid.uuid4().hex[:8])
            item.setdefault("created", time.strftime("%Y-%m-%d %H:%M:%S"))
            with LOCK:
                s = load()
                # atalho: o Jarvis pode mandar "biz": "UniGo" em vez do id
                if p[1] == "bizEntries" and not item.get("bizId") and item.get("biz"):
                    b = next((x for x in s["businesses"] if x["name"].lower() == str(item["biz"]).lower()), None)
                    if b: item["bizId"] = b["id"]
                s[p[1]].append(item)
                s["rev"] += 1
                log(s, self._source(), "adicionou", p[1], item)
                save(s)
            return self._send(201, item)
        if p == ["api", "pluggy", "connect-token"]:
            if not CFG.get("pluggy_client_id"):
                return self._send(400, {"erro": "Pluggy não configurado. Rode: py server.py --pluggy"})
            import pluggy_sync
            try:
                tok = pluggy_sync.Pluggy(CFG["pluggy_client_id"], CFG["pluggy_client_secret"]).connect_token()
            except Exception as e:
                return self._send(502, {"erro": f"Pluggy recusou: {e}. Confira Client ID/Secret."})
            return self._send(200, {"accessToken": tok})
        if p == ["api", "pluggy", "items"]:  # o widget avisa o ID do banco conectado -> salva sozinho
            item_id = str(self._body().get("itemId", "")).strip()
            if len(item_id) < 10:
                return self._send(400, {"erro": "itemId inválido"})
            cfg = load_config()
            items = cfg.setdefault("pluggy_items", [])
            if item_id not in items:
                items.append(item_id)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
            CFG["pluggy_items"] = items
            return self._send(200, run_pluggy())
        if p == ["api", "pluggy", "sync"]:
            if not CFG.get("pluggy_client_id"):
                return self._send(400, {"erro": "Pluggy não configurado. Rode: python server.py --pluggy"})
            return self._send(200, run_pluggy())
        if p == ["api", "replace"]:  # usado pelo site ao importar backup
            new = self._body()
            with LOCK:
                s = load()
                for c in COLLECTIONS:
                    if c in new: s[c] = new[c]
                s["rev"] += 1
                log(s, self._source(), "importou", "tudo", {"id": "backup"})
                save(s)
            return self._send(200, {"ok": True})
        return self._send(404, {"erro": "rota inválida"})

    def do_PATCH(self):
        p = self._parts()
        if not self._gate():
            return
        if len(p) == 3 and p[0] == "api" and p[1] in COLLECTIONS:
            patch = self._body()
            with LOCK:
                s = load()
                for it in s[p[1]]:
                    if it["id"] == p[2]:
                        it.update(patch)
                        s["rev"] += 1
                        log(s, self._source(), "editou", p[1], it)
                        save(s)
                        return self._send(200, it)
            return self._send(404, {"erro": "item não encontrado"})
        return self._send(404, {"erro": "rota inválida"})

    def do_DELETE(self):
        p = self._parts()
        if not self._gate():
            return
        if len(p) == 3 and p[0] == "api" and p[1] in COLLECTIONS:
            with LOCK:
                s = load()
                item = next((x for x in s[p[1]] if x["id"] == p[2]), None)
                if not item:
                    return self._send(404, {"erro": "item não encontrado"})
                s[p[1]] = [x for x in s[p[1]] if x["id"] != p[2]]
                if str(p[2]).startswith("pg_"):  # não reimportar o que você apagou
                    s["pluggyIgnored"].append(p[2])
                if p[1] == "businesses":  # apaga os lançamentos do negócio junto
                    s["bizEntries"] = [x for x in s["bizEntries"] if x.get("bizId") != p[2]]
                s["rev"] += 1
                log(s, self._source(), "removeu", p[1], item)
                save(s)
            return self._send(200, {"ok": True})
        return self._send(404, {"erro": "rota inválida"})


if __name__ == "__main__":
    if "--pluggy" in sys.argv:
        setup_pluggy()
        sys.exit(0)
    if "--set-password" in sys.argv:
        set_password()
        sys.exit(0)
    CFG = load_config()
    if "--port" in sys.argv:
        PORT = int(sys.argv[sys.argv.index("--port") + 1])
    load()
    if CFG.get("pluggy_client_id"):
        threading.Thread(target=pluggy_loop, daemon=True).start()
        print(f"Meu Pluggy: sincronizando a cada {CFG.get('pluggy_every_min', 60)} min")
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        print(f"\n[!] A porta {PORT} já está em uso: o ROTINA provavelmente já está aberto em outra janela.")
        print(f"    Abra http://localhost:{PORT} no navegador ou feche a outra janela.")
        sys.exit(1)
    print(f"\nROTINA rodando em http://localhost:{PORT}  (NÃO feche esta janela)")
    if "--no-browser" not in sys.argv:
        import webbrowser
        threading.Timer(0.8, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    httpd.serve_forever()
