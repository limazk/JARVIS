"""
JarvisAgent — orquestrador de alto nível.

Recebe uma entrada de texto (digitada ou transcrita da voz),
monta as peças (LLM, ferramentas, memória de curto prazo,
permissões) e devolve a resposta pronta para ser mostrada/falada.
Também mantém o AgentState atual, que a interface (ETAPA 6) usa
para mostrar ONLINE/PROCESSING/EXECUTING/etc.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from core.brain import build_llm_provider
from core.context import ConversationContext
from core.permissions import ConfirmCallback, PermissionManager
from core.performance import current_trace, request_trace
from core.router import Router
from core.state import AgentState
from tools.registry import build_default_registry
from tools.reminders import ReminderScheduler

logger = logging.getLogger("jarvis.agent")


class JarvisAgent:
    def __init__(
        self,
        confirm_callback: Optional[ConfirmCallback] = None,
        on_reminder_due: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.state = AgentState.OFFLINE
        self.context = ConversationContext()
        self.permissions = PermissionManager(confirm_callback=confirm_callback)
        self.tools = build_default_registry(self.permissions)
        self.llm = build_llm_provider()
        self.router = Router(self.llm, self.tools, self.context, self.permissions)

        # Hook chamado quando um lembrete vence (seção 21). Por padrão só
        # imprime no console; o modo voz (--voice) passa uma função que
        # também fala o aviso em voz alta.
        self._on_reminder_due = on_reminder_due or (lambda message: print(f"\n{message}\n"))
        self.reminder_scheduler = ReminderScheduler(on_due=self._on_reminder_due)
        self.reminder_scheduler.start()

        self.state = AgentState.ONLINE
        logger.info("Jarvis inicializado. LLM disponível: %s", self.llm.available)

    def shutdown(self) -> None:
        self.reminder_scheduler.stop()

    def process(self, user_text: str, response_mode: str = "text") -> str:
        if current_trace() is None:
            with request_trace() as trace:
                try:
                    return self._process(user_text, response_mode)
                finally:
                    trace.log()
        return self._process(user_text, response_mode)

    def _process(self, user_text: str, response_mode: str = "text") -> str:
        self.state = AgentState.PROCESSING
        try:
            result = self.router.handle(user_text, response_mode=response_mode)
        except Exception as exc:  # nunca deixa o agente derrubar o app (seção 42)
            logger.exception("Erro inesperado processando '%s'", user_text)
            self.state = AgentState.ERROR
            return f"Não consegui executar essa ação ({exc})."
        finally:
            if self.state != AgentState.ERROR:
                self.state = AgentState.ONLINE
        return result.reply
