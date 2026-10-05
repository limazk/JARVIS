"""
Sincronização Meu Pluggy -> ROTINA
----------------------------------
Puxa contas e transações dos seus bancos (via Meu Pluggy / Open Finance)
e lança automaticamente na aba Finanças. Só usa a biblioteca padrão.

Configurar:  python server.py --pluggy
Testar só:   python pluggy_sync.py
"""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.pluggy.ai"


class Pluggy:
    def __init__(self, client_id, client_secret):
        self.cid, self.secret = client_id, client_secret
        self.key, self.key_t = None, 0

    def _auth(self):
        if self.key and time.time() - self.key_t < 90 * 60:  # a chave vale ~2h
            return self.key
        body = json.dumps({"clientId": self.cid, "clientSecret": self.secret}).encode()
        req = urllib.request.Request(API + "/auth", data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            self.key = json.loads(r.read())["apiKey"]
        self.key_t = time.time()
        return self.key

    def get(self, path, params=None):
        url = path if path.startswith("http") else API + path
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"X-API-KEY": self._auth(), "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())

    def connect_token(self):
        req = urllib.request.Request(API + "/connect_token", data=b"{}", method="POST",
                                     headers={"X-API-KEY": self._auth(), "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())["accessToken"]

    def item(self, item_id):
        return self.get(f"/items/{item_id}")

    def accounts(self, item_id):
        return self.get("/accounts", {"itemId": item_id}).get("results", [])

    def _get_tolerant(self, path, params):
        """Se a Pluggy responder 'property X should not exist', tira X e tenta de novo."""
        params = dict(params or {})
        for _ in range(5):
            try:
                return self.get(path, params or None)
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", "ignore")
                m = re.search(r"property (\w+) should not exist", body)
                if e.code == 400 and m and m.group(1) in params:
                    params.pop(m.group(1))
                    continue
                raise urllib.error.HTTPError(e.url, e.code, body[:300], e.headers, None)
        return self.get(path, params or None)

    def transactions(self, account_id, date_from):
        """GET /v2/transactions com paginação por cursor (o /transactions antigo foi desativado)."""
        out, seen = [], set()
        path, params = "/v2/transactions", {"accountId": account_id, "dateFrom": date_from}
        for _ in range(40):  # trava de segurança
            data = self._get_tolerant(path, params)
            for t in data.get("results", []):
                if t.get("id") not in seen:
                    seen.add(t.get("id"))
                    out.append(t)
            nxt = data.get("next")
            if not nxt:
                break
            # "next" pode vir como URL completa, caminho, query string ou só o cursor
            if nxt.startswith("http") or nxt.startswith("/"):
                path, params = nxt, None
            elif nxt.startswith("?"):
                path, params = "/v2/transactions" + nxt, None
            else:
                path, params = "/v2/transactions", {"accountId": account_id, "cursor": nxt}
        # se a data não foi aceita como filtro, corta aqui
        return [t for t in out if (t.get("date") or "")[:10] >= date_from]


# categorias da Pluggy (em inglês) -> categorias do ROTINA
CAT_MAP = [("salary", "Salário"), ("food", "Alimentação"), ("groceries", "Alimentação"), ("restaurant", "Alimentação"),
           ("transport", "Transporte"), ("uber", "Transporte"), ("fuel", "Transporte"), ("gas station", "Transporte"),
           ("rent", "Moradia"), ("housing", "Moradia"), ("utilities", "Moradia"), ("education", "Faculdade"),
           ("leisure", "Lazer"), ("entertainment", "Lazer"), ("digital services", "Assinaturas"),
           ("subscription", "Assinaturas"), ("streaming", "Assinaturas")]


def map_cat(cat):
    c = (cat or "").lower()
    for k, v in CAT_MAP:
        if k in c:
            return v
    return "Banco"


def sync(state, cfg, log_fn=None):
    """Atualiza `state` (o mesmo dict do data.json). Retorna um resumo."""
    pl = Pluggy(cfg["pluggy_client_id"], cfg["pluggy_client_secret"])
    days = int(cfg.get("pluggy_days", 90))
    include_cards = bool(cfg.get("pluggy_include_cards", False))
    date_from = time.strftime("%Y-%m-%d", time.localtime(time.time() - days * 86400))
    known = {t["id"] for t in state["transactions"]}
    bank_accounts, new, errors = [], 0, []

    for item_id in cfg.get("pluggy_items", []):
        try:
            item = pl.item(item_id)
            bank = (item.get("connector") or {}).get("name", "Banco")
            status = item.get("status")
            for acc in pl.accounts(item_id):
                is_card = acc.get("type") == "CREDIT"
                bank_accounts.append({
                    "id": acc["id"], "bank": bank, "name": acc.get("name") or acc.get("marketingName") or "Conta",
                    "type": "cartão" if is_card else "conta", "balance": acc.get("balance", 0),
                    "status": status, "updated": item.get("lastUpdatedAt") or item.get("updatedAt"),
                })
                if is_card and not include_cards:
                    continue  # fatura do cartão duplicaria os gastos; liga com pluggy_include_cards
                for tx in pl.transactions(acc["id"], date_from):
                    tid = "pg_" + tx["id"]
                    if tid in known or tx.get("status") == "PENDING":
                        continue
                    amt = float(tx.get("amount", 0))
                    typ = tx.get("type")
                    if is_card:  # no cartão, compra = gasto
                        kind = "in" if amt < 0 else "out"
                    else:
                        kind = "in" if (typ == "CREDIT" or (typ is None and amt > 0)) else "out"
                    state["transactions"].append({
                        "id": tid, "type": kind, "amount": abs(amt),
                        "desc": (tx.get("description") or "—")[:120], "cat": map_cat(tx.get("category")),
                        "date": (tx.get("date") or "")[:10], "bank": bank, "source": "pluggy",
                        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                    })
                    known.add(tid)
                    new += 1
        except urllib.error.HTTPError as e:
            errors.append(f"{item_id[:8]}: HTTP {e.code} {str(e.msg)[:200]}")
        except Exception as e:  # rede fora, etc.
            errors.append(f"{item_id[:8]}: {e}")

    if bank_accounts or not errors:
        state["bankAccounts"] = bank_accounts
    state["pluggy"] = {"last": time.strftime("%Y-%m-%d %H:%M:%S"), "new": new, "errors": errors}
    if new:
        state["rev"] = state.get("rev", 0) + 1
        if log_fn:
            log_fn(state, "pluggy", "importou", "transactions", {"desc": f"{new} transações do banco"})
    return state["pluggy"]


if __name__ == "__main__":
    import os
    base = os.path.dirname(os.path.abspath(__file__))
    cfg = json.load(open(os.path.join(base, "config.json"), encoding="utf-8"))
    pl = Pluggy(cfg["pluggy_client_id"], cfg["pluggy_client_secret"])
    for it in cfg.get("pluggy_items", []):
        i = pl.item(it)
        print(f"\n== {(i.get('connector') or {}).get('name')}  status={i.get('status')}")
        for a in pl.accounts(it):
            print(f"   {a.get('type'):7} {a.get('name')}: R$ {a.get('balance')}")
