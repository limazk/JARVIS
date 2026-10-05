"""
Router central do Jarvis — seção 32 do spec.

Fluxo:
    mensagem -> intent local -> (fallback) LLM decide -> permissão -> execução -> resposta

O router é o único lugar que decide "isso vira uma ação real". Ele
nunca deixa o texto do LLM ser reportado como "ação concluída" sem
que a tool correspondente tenha retornado success=True — e nunca
executa código Python enviado como texto pelo usuário ou pelo LLM.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from config.settings import settings
from core.brain import LLMProvider
from core.context import ConversationContext
from core.intent import match_local_intent
from core.permissions import PermissionDenied, PermissionManager
from core.performance import measure
from core.specialists import pick_specialist
from personality.engine import PersonalityEngine
from memory import conversations as conversation_log
from memory import memory as long_term_memory
from memory.database import log_activity
from tools.registry import ToolRegistry

logger = logging.getLogger("jarvis.router")

_FAST_DIRECT_READ_TOOLS = {
    "get_today_tasks", "get_rotina_summary", "get_financial_summary",
    "get_weekly_finance", "get_business_summary", "get_weekly_productivity",
    "compare_weekly_finance", "list_reminders", "list_upcoming_events",
    "system_status", "disk_space",
}

SYSTEM_PROMPT = """Quando o usuário pedir uma ação que existe como ferramenta, chame a ferramenta —
nunca diga que fez algo sem realmente ter chamado a ferramenta correspondente.
Se não houver ferramenta para o que foi pedido, diga isso honestamente.
Sempre que o usuário contar um fato, dado ou preferência pessoal sobre ele mesmo
(nome, apelido, onde mora ou trabalha, o que gosta/não gosta, ferramentas que usa,
pessoas importantes para ele, rotinas, etc.), chame a ferramenta remember_fact para
guardar isso — mesmo que ele não peça explicitamente para "lembrar". É melhor
guardar um fato a mais do que esquecer algo que ele já contou."""


def _build_system_prompt(response_mode: str = "text", current_mode: str = "NORMAL") -> str:
    """
    Monta o system prompt base + a data/hora atual + a instrução de
    forma de tratamento (USER_TITLE, ex.: "Senhor"). Isso fica FORA de
    `recall_relevant` (que só injeta memórias relevantes por palavra-
    chave) de propósito: tanto a data atual quanto a forma de
    tratamento têm que valer em toda mensagem, não só nas que "parecem"
    relevantes por busca de texto.

    A data/hora atual importa principalmente pra tools/gcalendar.py
    (criar compromisso a partir de "amanhã às 15h" exige saber que dia
    é hoje) — mas ajuda em qualquer resposta que dependa de tempo.
    """
    now = datetime.now()
    dias_semana = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
    personality = PersonalityEngine(current_mode=current_mode)
    prompt = (
        f"{personality.system_prompt(response_mode=response_mode)}\n\n{SYSTEM_PROMPT}\n\n"
        f"Data e hora atuais: {dias_semana[now.weekday()]}, {now.strftime('%d/%m/%Y às %H:%M')} "
        f"(formato ISO: {now.isoformat(timespec='seconds')})."
    )
    if settings.user_title.strip():
        title = settings.user_title.strip()
        prompt += (
            f"\n\nSempre se dirija ao usuário chamando-o de \"{title}\" "
            f"(ex.: \"Sim, {title}.\", \"Encontrei isso, {title}.\", \"Pronto, {title}.\"). "
            f"Use \"{title}\" em vez do nome dele ou de qualquer outro pronome de tratamento, "
            f"em toda resposta onde fizer sentido dirigir-se a ele diretamente."
        )
    return prompt


@dataclass
class RouterResult:
    reply: str
    tool_used: Optional[str] = None
    success: bool = True


class Router:
    def __init__(
        self,
        llm: LLMProvider,
        tools: ToolRegistry,
        context: ConversationContext,
        permissions: PermissionManager,
    ) -> None:
        self.llm = llm
        self.tools = tools
        self.context = context
        self.permissions = permissions
        # Nome do último especialista (core/specialists.py) selecionado
        # numa mensagem que foi mesmo pro LLM (None = modo geral, sem
        # especialista, ou ainda nenhuma mensagem assim). Exposto via
        # `last_specialist` pra a interface poder mostrar em que "modo"
        # o Jarvis está (ver interface_web/bridge.py::get_snapshot).
        self._last_specialist_name: Optional[str] = None

    @property
    def last_specialist(self) -> Optional[str]:
        return self._last_specialist_name

    def handle(self, user_text: str, response_mode: str = "text") -> RouterResult:
        start = time.perf_counter()
        self.context.add("user", user_text)
        conversation_log.log_message("user", user_text)

        # 1) Tenta o parser local primeiro (rápido, grátis, offline).
        with measure("routing_duration"):
            intent = match_local_intent(user_text)
        tool_name = intent.tool_name
        tool_input = intent.params

        if not intent.matched:
            # 2) Não bateu nenhum padrão local -> pergunta ao LLM, com
            #    tool-calling, o que fazer (conversar ou chamar uma tool).
            # Antes, busca na memória de longo prazo só o que for relevante
            # para esta pergunta (nunca manda o banco inteiro — seção 30).
            system_prompt = _build_system_prompt(response_mode=response_mode)
            relevant_memories = long_term_memory.recall_relevant(user_text)
            if relevant_memories:
                facts = "\n".join(f"- {fact}" for fact in relevant_memories)
                system_prompt += f"\n\nFatos que você já sabe sobre o usuário:\n{facts}"

            # Seção 49: escolhe um "especialista" por palavra-chave (sem custo
            # extra de API) e aplica as 3 coisas dele no mesmo prompt/lista de
            # tools desta ÚNICA chamada — ver core/specialists.py para o porquê
            # disso não vira múltiplas chamadas de LLM (mantém a resposta
            # rápida em vez de virar um "multi-agente" de verdade e mais lento).
            specialist = pick_specialist(user_text)
            tool_schemas = self.tools.as_llm_tool_schemas()
            if specialist is not None:
                system_prompt += f"\n\n{specialist.extra_prompt}"

                if specialist.context_builder is not None:
                    try:
                        extra_context = specialist.context_builder()
                    except Exception:  # nunca deixa o contexto extra derrubar a mensagem
                        extra_context = ""
                        logger.warning("context_builder do especialista '%s' falhou.", specialist.name)
                    if extra_context:
                        system_prompt += f"\n\n{extra_context}"

                if specialist.preferred_tools:
                    tool_schemas = self.tools.as_llm_tool_schemas(prioritize=specialist.preferred_tools)

                if settings.debug:
                    logger.debug("Especialista selecionado: %s", specialist.name)

                if specialist.name != self._last_specialist_name:
                    log_activity(f"Modo especialista: {specialist.name}")
                self._last_specialist_name = specialist.name
            else:
                self._last_specialist_name = None

            with measure("llm_total_duration"):
                decision = self.llm.decide(
                    system_prompt=system_prompt,
                    messages=self.context.as_llm_messages(),
                    tools=tool_schemas,
                )
            if decision.kind == "text":
                reply = decision.text or ""
                self.context.add("assistant", reply)
                conversation_log.log_message("assistant", reply)
                self._log_debug(user_text, None, {}, reply, start)
                return RouterResult(reply=reply)
            tool_name = decision.tool_name
            tool_input = decision.tool_input

        result = self._execute_tool(tool_name, tool_input)
        if intent.matched and tool_name in _FAST_DIRECT_READ_TOOLS:
            result.reply = PersonalityEngine().apply_direct(result.reply, response_mode=response_mode)
        self.context.add("assistant", result.reply)
        conversation_log.log_message("assistant", result.reply)
        self._log_debug(user_text, tool_name, tool_input, result.reply, start)
        return result

    def _execute_tool(self, tool_name: Optional[str], tool_input: dict) -> RouterResult:
        tool = self.tools.get(tool_name) if tool_name else None
        if tool is None:
            msg = f"Ainda não tenho a ferramenta '{tool_name}' implementada."
            return RouterResult(reply=msg, tool_used=tool_name, success=False)

        description = tool.describe_action(**tool_input)
        try:
            self.permissions.check(tool.name, tool.risk_level, description)
        except PermissionDenied as exc:
            return RouterResult(reply=str(exc), tool_used=tool.name, success=False)

        with measure("tool_duration"):
            outcome = tool.execute(**tool_input)
        if outcome.success:
            # Alimenta o painel de ATIVIDADE da interface (seções 10/55).
            log_activity(description)
        return RouterResult(reply=outcome.message, tool_used=tool.name, success=outcome.success)

    @staticmethod
    def _log_debug(user_text: str, tool_name: Optional[str], params: dict, reply: str, start: float) -> None:
        if not settings.debug:
            return
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.debug(
            "entrada=%r tool=%r params=%r resposta=%r tempo=%.1fms",
            user_text, tool_name, params, reply, elapsed_ms,
        )
