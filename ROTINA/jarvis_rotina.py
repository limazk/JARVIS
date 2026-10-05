"""
Ponte Jarvis <-> ROTINA
-----------------------
Copie este arquivo para a pasta tools/ do Jarvis e registre as funções
no ToolRegistry. Usa só urllib (biblioteca padrão).

O servidor do ROTINA (server.py) precisa estar rodando.
No .env do Jarvis:
    ROTINA_URL=http://localhost:8765
    ROTINA_KEY=<chave que o server.py mostrou>
"""
import json
import os
import time
import urllib.error
import urllib.request

URL = os.getenv("ROTINA_URL", "http://localhost:8765").rstrip("/")
KEY = os.getenv("ROTINA_KEY", "")  # mostrada pelo server.py ao criar a senha


def _req(method, path, body=None, timeout=5):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    r = urllib.request.Request(URL + path, data=data, method=method,
                               headers={"Content-Type": "application/json", "X-Api-Key": KEY})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise RuntimeError("ROTINA recusou X-Api-Key; confira ROTINA_KEY.") from exc
        raise RuntimeError(f"ROTINA respondeu HTTP {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"ROTINA indisponível em {URL}: {exc}") from exc


def _hoje():
    return time.strftime("%Y-%m-%d")


# ---------------- ROTINA ----------------
def adicionar_tarefa(titulo, horario="", categoria="Pessoal", prioridade="media",
                     data=None, recorrencia="none", dia_semana=None):
    """recorrencia: none | daily | weekly (weekly usa dia_semana 0=dom..6=sáb)"""
    return _req("POST", "/api/tasks", {
        "title": titulo, "time": horario, "cat": categoria, "prio": prioridade,
        "date": data or _hoje(), "recur": recorrencia,
        "weekday": dia_semana if dia_semana is not None else int(time.strftime("%w")),
        "doneDates": []})


def concluir_tarefa(titulo_ou_id, data=None):
    d = data or _hoje()
    for t in _req("GET", "/api/tasks"):
        if t["id"] == titulo_ou_id or titulo_ou_id.lower() in t["title"].lower():
            done = list(set((t.get("doneDates") or []) + [d]))
            return _req("PATCH", f"/api/tasks/{t['id']}", {"doneDates": done})
    return {"erro": "tarefa não encontrada"}


# ---------------- IDEIAS ----------------
def adicionar_ideia(texto, tag="geral"):
    return _req("POST", "/api/ideas", {"text": texto, "tag": tag})


# ---------------- DINHEIRO ----------------
def lancar_dinheiro(tipo, valor, descricao, categoria="Outros", data=None):
    """tipo: 'in' (entrada) ou 'out' (saída)"""
    return _req("POST", "/api/transactions", {
        "type": tipo, "amount": float(valor), "desc": descricao, "cat": categoria, "date": data or _hoje()})


# ---------------- NEGÓCIOS ----------------
def lancar_negocio(negocio, tipo, valor, descricao="", data=None):
    """negocio: nome (ex 'UniGo'); tipo: revenue | cost | invest | withdraw"""
    return _req("POST", "/api/bizEntries", {
        "biz": negocio, "type": tipo, "amount": float(valor), "desc": descricao, "date": data or _hoje()})


def criar_negocio(nome, status="ativo"):
    return _req("POST", "/api/businesses", {"name": nome, "status": status, "color": "#ffffff"})


def metricas_negocio(nome):
    return _req("GET", "/api/businesses/" + urllib.request.quote(nome))


# ---------------- INVESTIMENTOS ----------------
def adicionar_investimento(nome, aplicado, tipo="Outro", atual=None, data=None):
    return _req("POST", "/api/investments", {
        "name": nome, "kind": tipo, "invested": float(aplicado),
        "current": float(atual if atual is not None else aplicado), "date": data or _hoje()})


def atualizar_investimento(nome, valor_atual):
    for i in _req("GET", "/api/investments"):
        if nome.lower() in i["name"].lower():
            return _req("PATCH", f"/api/investments/{i['id']}", {"current": float(valor_atual)})
    return {"erro": "investimento não encontrado"}


# ---------------- GERAL ----------------
def health():
    return _req("GET", "/api/health", timeout=2)


def summary():
    return _req("GET", "/api/summary")


def tasks():
    return _req("GET", "/api/tasks")


def transactions():
    return _req("GET", "/api/transactions")


def businesses():
    return _req("GET", "/api/businesses")


def weekly_summary():
    return _req("GET", "/api/summary?period=week")


def remover(colecao, item_id):
    """colecao: tasks | ideas | transactions | businesses | bizEntries | investments"""
    return _req("DELETE", f"/api/{colecao}/{item_id}")


def listar(colecao):
    return _req("GET", f"/api/{colecao}")


def resumo():
    """Tudo num JSON só: rotina de hoje, saldo, lucro por negócio, retorno dos investimentos."""
    return _req("GET", "/api/summary")


# Mapa pronto pra registrar no ToolRegistry do Jarvis
TOOLS = {
    "rotina_adicionar_tarefa": adicionar_tarefa,
    "rotina_concluir_tarefa": concluir_tarefa,
    "rotina_adicionar_ideia": adicionar_ideia,
    "rotina_lancar_dinheiro": lancar_dinheiro,
    "rotina_lancar_negocio": lancar_negocio,
    "rotina_criar_negocio": criar_negocio,
    "rotina_metricas_negocio": metricas_negocio,
    "rotina_adicionar_investimento": adicionar_investimento,
    "rotina_atualizar_investimento": atualizar_investimento,
    "rotina_remover": remover,
    "rotina_listar": listar,
    "rotina_resumo": resumo,
    "rotina_resumo_semanal": weekly_summary,
}

if __name__ == "__main__":
    print(json.dumps(resumo(), ensure_ascii=False, indent=2))
