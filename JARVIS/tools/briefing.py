"""
Resumo da manhã ("bom dia") — pedido depois que o usuário mandou um
vídeo de referência de um "briefing matinal" ambiente (tela cheia,
orbe, cards de clima/agenda/e-mail/prioridades falados em sequência
assim que a pessoa diz "bom dia").

Esta é a versão real e funcional da ideia: não é uma ferramenta nova
"de API" — é uma ORQUESTRAÇÃO LOCAL das ferramentas que o Jarvis já
tem (clima, e-mails não lidos, agenda do dia, lembretes pendentes) mais
um resumo do que foi guardado na memória de longo prazo desde ontem.
Tudo roda em chamadas Python diretas, sem LLM e sem nenhuma chamada de
API a mais do que cada ferramenta já faria sozinha — mesmo espírito
"pré-instantâneo" dos comandos locais (core/intent.py) e dos
especialistas (core/specialists.py).

Cada seção só entra no resumo se tiver um dado real pra mostrar: se o
Google não estiver configurado (sem Gmail/Calendar) ou alguma consulta
falhar (sem internet, clima fora do ar, etc.), aquela seção é omitida
em silêncio — o briefing nunca inventa um dado que não conseguiu buscar
de verdade.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable

from config.settings import settings
from core.permissions import RiskLevel
from memory.database import get_connection
from tools.base import Tool, ToolResult


def _recap_desde_ontem() -> str:
    """Fatos novos guardados na memória de longo prazo (remember_fact) nas últimas 24h, se houver algum."""
    try:
        limite = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT value FROM memories WHERE created_at >= ? ORDER BY id DESC LIMIT 5",
                (limite,),
            ).fetchall()
    except Exception:
        return ""
    if not rows:
        return ""
    itens = "; ".join(r["value"] for r in rows)
    return f"Desde ontem, guardei: {itens}."


def _secao(fn: Callable[..., ToolResult], *args: object, **kwargs: object) -> str:
    """
    Chama uma ferramenta já existente e devolve só a mensagem dela — ou
    "" se a ferramenta não estiver configurada, falhar, ou levantar
    qualquer exceção. Uma seção indisponível nunca pode derrubar o resto
    do briefing nem virar um texto de erro confuso no meio do resumo.
    """
    try:
        result = fn(*args, **kwargs)
    except Exception:
        return ""
    return result.message if result.success else ""


def morning_briefing(**_: object) -> ToolResult:
    # Imports aqui dentro (não no topo do módulo) seguem o mesmo padrão
    # usado em core/specialists.py — evita qualquer risco de import
    # circular entre tools/ e deixa claro que isso só é tocado quando o
    # briefing é de fato pedido.
    from tools.gcalendar import list_upcoming_events
    from tools.gmail import list_unread_emails
    from tools.reminders import list_reminders
    from tools.weather import get_weather

    saudacao = f"Bom dia, {settings.user_title}." if settings.user_title.strip() else "Bom dia."

    secoes = [
        _recap_desde_ontem(),
        _secao(get_weather, day="hoje"),
        _secao(list_upcoming_events, days=1),
        _secao(list_unread_emails, limit=5),
        _secao(list_reminders),
    ]
    secoes = [s for s in secoes if s]

    if not secoes:
        texto = (
            f"{saudacao} Não tenho nenhuma atualização nova pra te passar agora "
            "(ou as integrações de e-mail/agenda ainda não estão configuradas)."
        )
    else:
        texto = saudacao + "\n\n" + "\n\n".join(secoes)

    return ToolResult(success=True, message=texto, data={"secoes": len(secoes)})


def register(registry) -> None:
    registry.register(Tool(
        name="morning_briefing",
        description=(
            "Monta um resumo matinal completo e fala em voz alta: o que foi guardado na memória "
            "desde ontem, previsão do tempo de hoje, agenda do dia, e-mails não lidos e lembretes "
            "pendentes. Use quando o usuário disser 'bom dia' ou pedir um resumo/briefing da manhã."
        ),
        parameters={"type": "object", "properties": {}},
        risk_level=RiskLevel.LOW,
        handler=morning_briefing,
    ))
