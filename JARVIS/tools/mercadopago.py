"""
Integração com o Mercado Pago — consulta de vendas recentes, criação
de links de cobrança e saldo (relatório de liquidação), seguindo o
mesmo padrão de tools/github.py e tools/spotify.py.

Como gerar o Access Token (grátis, ~2 minutos):
    Painel do Mercado Pago (https://www.mercadopago.com.br/developers/panel)
    → "Suas integrações" → crie uma aplicação → aba "Credenciais de
    produção" (ou "Credenciais de teste", pra testar sem mexer com
    dinheiro de verdade) → copie o "Access Token".
Cole o valor em MERCADOPAGO_ACCESS_TOKEN no .env. Sem o token, nenhuma
das funções deste módulo funciona — mas o resto do Jarvis continua
normal, com um aviso honesto em vez de erro confuso.

Sobre "saldo" (mercadopago_saldo): o Mercado Pago NÃO tem um endpoint
que devolva "quanto eu tenho disponível agora" instantaneamente. O
mais perto disso é o relatório de liquidação (settlement report):
você pede o relatório de um período, o Mercado Pago gera um CSV (isso
leva alguns segundos, às vezes minutos) e só então dá pra somar o
valor líquido. `mercadopago_saldo` pede o relatório e espera um
pouco — se não ficar pronto a tempo, o Jarvis avisa isso claramente
em vez de inventar um número. Não é um "saldo da carteira" em tempo
real, é o valor líquido liquidado no período consultado.
"""
from __future__ import annotations

import csv
import io
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from config.settings import settings
from core.permissions import PermissionDenied, PermissionManager, RiskLevel
from tools.base import Tool, ToolResult

_API_BASE = "https://api.mercadopago.com"

_SALDO_POLL_TENTATIVAS = 5
_SALDO_POLL_INTERVALO = 2.0  # segundos entre tentativas de checar se o relatório ficou pronto

_STATUS_PT = {
    "approved": "aprovado",
    "pending": "pendente",
    "in_process": "em análise",
    "rejected": "recusado",
    "refunded": "estornado",
    "cancelled": "cancelado",
    "in_mediation": "em mediação",
    "charged_back": "chargeback",
}


def _mp_headers() -> Optional[dict]:
    if not settings.mercadopago_access_token:
        return None
    return {
        "Authorization": f"Bearer {settings.mercadopago_access_token}",
        "Content-Type": "application/json",
    }


def _no_credentials_result() -> ToolResult:
    return ToolResult(
        success=False,
        message=(
            "Preciso de um MERCADOPAGO_ACCESS_TOKEN no .env para falar com o Mercado Pago "
            "(veja o topo de tools/mercadopago.py ou o README para gerar o seu, grátis)."
        ),
    )


def mercadopago_vendas_recentes(dias: int = 7, **_: object) -> ToolResult:
    """Lista os pagamentos/vendas mais recentes (últimos `dias` dias, padrão 7)."""
    headers = _mp_headers()
    if headers is None:
        return _no_credentials_result()

    dias = max(1, int(dias))
    try:
        import requests

        begin = (datetime.now(timezone.utc) - timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%S.000-00:00")
        end = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000-00:00")
        resp = requests.get(
            f"{_API_BASE}/v1/payments/search",
            headers=headers,
            params={
                "range": "date_created",
                "begin_date": begin,
                "end_date": end,
                "sort": "date_created",
                "criteria": "desc",
                "limit": 20,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return ToolResult(success=False, message=f"Não consegui consultar o Mercado Pago: {exc}")

    results = data.get("results", [])
    if not results:
        return ToolResult(success=True, message=f"Nenhuma venda encontrada nos últimos {dias} dia(s).", data={"vendas": []})

    aprovados = [r for r in results if r.get("status") == "approved"]
    total_aprovado = sum((r.get("transaction_amount") or 0) for r in aprovados)
    moeda = results[0].get("currency_id", "BRL")

    linhas = []
    for r in results[:10]:
        status_pt = _STATUS_PT.get(r.get("status"), r.get("status"))
        valor = r.get("transaction_amount") or 0
        descricao = r.get("description") or "sem descrição"
        linhas.append(f"- {moeda} {valor:.2f} ({status_pt}) — {descricao}")

    resumo = (
        f"{len(results)} venda(s) nos últimos {dias} dia(s) "
        f"({len(aprovados)} aprovada(s), total {moeda} {total_aprovado:.2f}):\n" + "\n".join(linhas)
    )
    return ToolResult(success=True, message=resumo, data={"vendas": results})


def mercadopago_criar_cobranca(
    titulo: str, valor: float, descricao: str = "", email_comprador: str = "", **_: object
) -> ToolResult:
    """Cria um link de pagamento (cobrança) do Mercado Pago, pronto pra enviar ao cliente."""
    headers = _mp_headers()
    if headers is None:
        return _no_credentials_result()

    try:
        import requests

        item = {"title": titulo, "quantity": 1, "unit_price": float(valor), "currency_id": "BRL"}
        if descricao:
            item["description"] = descricao
        body: dict = {"items": [item]}
        if email_comprador:
            body["payer"] = {"email": email_comprador}

        resp = requests.post(f"{_API_BASE}/checkout/preferences", headers=headers, json=body, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return ToolResult(success=False, message=f"Não consegui criar a cobrança no Mercado Pago: {exc}")

    link = data.get("init_point") or data.get("sandbox_init_point")
    if not link:
        return ToolResult(
            success=False,
            message="O Mercado Pago aceitou a cobrança mas não devolveu um link de pagamento — tente de novo.",
        )
    return ToolResult(
        success=True,
        message=f"Cobrança criada: '{titulo}' (R$ {float(valor):.2f}). Link para enviar ao cliente: {link}",
        data=data,
    )


def mercadopago_saldo(dias: int = 30, **_: object) -> ToolResult:
    """
    Consulta o valor líquido liquidado no Mercado Pago no período (ver
    nota no topo do arquivo: não existe "saldo instantâneo" na API —
    isso é o relatório de liquidação resumido).
    """
    headers = _mp_headers()
    if headers is None:
        return _no_credentials_result()

    dias = max(1, int(dias))
    begin = (datetime.now(timezone.utc) - timedelta(days=dias)).strftime("%Y-%m-%d")
    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    try:
        import requests

        resp = requests.post(
            f"{_API_BASE}/v1/account/settlement_report",
            headers=headers,
            json={"begin_date": begin, "end_date": end},
            timeout=15,
        )
        if resp.status_code not in (200, 202):
            resp.raise_for_status()
    except Exception as exc:
        return ToolResult(success=False, message=f"Não consegui pedir o relatório de saldo ao Mercado Pago: {exc}")

    file_name = None
    try:
        import requests

        for _ in range(_SALDO_POLL_TENTATIVAS):
            time.sleep(_SALDO_POLL_INTERVALO)
            list_resp = requests.get(f"{_API_BASE}/v1/account/settlement_report/list", headers=headers, timeout=15)
            list_resp.raise_for_status()
            reports = list_resp.json()
            if isinstance(reports, dict):
                reports = reports.get("response") or reports.get("results") or []
            if reports:
                file_name = reports[0].get("file_name")
                if file_name:
                    break
    except Exception as exc:
        return ToolResult(success=False, message=f"Não consegui checar se o relatório de saldo ficou pronto: {exc}")

    if not file_name:
        return ToolResult(
            success=False,
            message=(
                "O Mercado Pago ainda está gerando o relatório de saldo — isso pode levar "
                "alguns minutos. Peça de novo daqui a pouco."
            ),
        )

    try:
        import requests

        file_resp = requests.get(f"{_API_BASE}/v1/account/settlement_report/{file_name}", headers=headers, timeout=20)
        file_resp.raise_for_status()
        reader = csv.DictReader(io.StringIO(file_resp.text))
        total = 0.0
        linhas = 0
        for row in reader:
            valor = row.get("SETTLEMENT_NET_AMOUNT")
            if valor:
                try:
                    total += float(valor)
                    linhas += 1
                except ValueError:
                    continue
    except Exception as exc:
        return ToolResult(success=False, message=f"Não consegui baixar/ler o relatório de saldo: {exc}")

    if linhas == 0:
        return ToolResult(
            success=True,
            message=f"Nenhuma movimentação liquidada nos últimos {dias} dia(s).",
            data={"total": 0.0, "dias": dias},
        )

    return ToolResult(
        success=True,
        message=(
            f"Valor líquido liquidado nos últimos {dias} dia(s): R$ {total:.2f} "
            "(baseado no relatório de liquidação do Mercado Pago — não é o saldo da carteira em tempo real)."
        ),
        data={"total": total, "dias": dias},
    )


def register(registry, permissions: Optional[PermissionManager] = None) -> None:
    registry.register(Tool(
        name="mercadopago_vendas_recentes",
        description="Lista as vendas/pagamentos recentes no Mercado Pago (requer MERCADOPAGO_ACCESS_TOKEN configurado).",
        parameters={"type": "object", "properties": {"dias": {"type": "integer"}}},
        risk_level=RiskLevel.LOW,
        handler=mercadopago_vendas_recentes,
    ))
    registry.register(Tool(
        name="mercadopago_saldo",
        description=(
            "Consulta o valor líquido liquidado no Mercado Pago em um período, via relatório de "
            "liquidação (pode levar alguns segundos — não é um saldo instantâneo de carteira)."
        ),
        parameters={"type": "object", "properties": {"dias": {"type": "integer"}}},
        risk_level=RiskLevel.LOW,
        handler=mercadopago_saldo,
    ))

    def criar_cobranca_handler(
        titulo: str, valor: float, descricao: str = "", email_comprador: str = "", **_: object
    ) -> ToolResult:
        if permissions is not None:
            try:
                permissions.check(
                    "mercadopago_criar_cobranca",
                    RiskLevel.MEDIUM,
                    f"Criar cobrança de R$ {float(valor):.2f} no Mercado Pago: '{titulo}'",
                )
            except PermissionDenied as exc:
                return ToolResult(success=False, message=str(exc))
        return mercadopago_criar_cobranca(titulo, valor, descricao, email_comprador)

    registry.register(Tool(
        name="mercadopago_criar_cobranca",
        description="Cria um link de cobrança/pagamento no Mercado Pago pra enviar a um cliente. Exige confirmação.",
        parameters={
            "type": "object",
            "properties": {
                "titulo": {"type": "string"},
                "valor": {"type": "number"},
                "descricao": {"type": "string"},
                "email_comprador": {"type": "string"},
            },
            "required": ["titulo", "valor"],
        },
        risk_level=RiskLevel.MEDIUM,
        handler=criar_cobranca_handler,
        confirmation_template="Criar cobrança de R$ {valor:.2f} no Mercado Pago: '{titulo}'",
    ))
