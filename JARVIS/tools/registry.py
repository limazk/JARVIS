"""
Registro central de ferramentas.

Cada módulo em tools/ (apps.py, system.py, ...) expõe uma função
register(registry, permissions=None) que adiciona suas Tools aqui.
O router só conhece este registro — nunca importa um módulo de tool
diretamente. `permissions` é passado para os módulos que precisam
fazer sua própria checagem dinâmica (shell.py, github.py); os
demais simplesmente ignoram o parâmetro.
"""
from __future__ import annotations

from typing import Optional

from core.permissions import PermissionManager
from tools.base import Tool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        # Preenchido por plugins.bridge no fim de build_default_registry().
        self.plugin_registry = None

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool duplicada: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def all(self):
        return self._tools.values()

    def as_llm_tool_schemas(self, prioritize: tuple[str, ...] = ()) -> list[dict]:
        """
        Formato de 'tools' aceito pela API de tool-calling da Anthropic
        (e, via core/brain.py::_OpenAICompatibleProvider, convertido pro
        formato da OpenAI/Gemini/Groq/Ollama também).

        `prioritize` (usado por core/router.py quando um especialista foi
        selecionado — ver core/specialists.py) só REORDENA a lista pra
        colocar essas ferramentas primeiro; nunca remove nenhuma. O
        Jarvis sempre pode usar qualquer ferramenta registrada, mesmo
        fora do "assunto" detectado — isso só ajuda o modelo a notar mais
        rápido a ferramenta mais provável pro pedido atual.
        """
        schemas = [
            {"name": t.name, "description": t.description, "input_schema": t.parameters}
            for t in self._tools.values()
        ]
        if not prioritize:
            return schemas
        priority = set(prioritize)
        # sort() é estável: dentro de cada grupo (priorizado / não
        # priorizado) a ordem relativa original é preservada.
        schemas.sort(key=lambda s: 0 if s["name"] in priority else 1)
        return schemas


def build_default_registry(permissions: Optional[PermissionManager] = None) -> ToolRegistry:
    """Monta o registro com todas as ferramentas disponíveis."""
    registry = ToolRegistry()

    from memory import memory as long_term_memory
    from tools import (
        apps,
        briefing,
        browser,
        calculator,
        clipboard,
        files,
        gcalendar,
        gdrive,
        github,
        gmail,
        mercadopago,
        notes,
        rotina,
        reminders,
        screenshot,
        search,
        shell,
        spotify,
        system,
        timers,
        vision,
        weather,
    )

    for module in (apps, briefing, browser, calculator, clipboard, files, notes, rotina, long_term_memory,
                   reminders, screenshot, search, spotify, system, timers, vision, weather,
                   gmail, gcalendar, gdrive):
        module.register(registry)

    # Módulos que precisam da instância de PermissionManager para checagem dinâmica.
    for module in (shell, github, mercadopago):
        module.register(registry, permissions)

    # Plugins ficam por cima das Tools existentes. O bridge registra
    # list_plugins/plugin_status/plugin_execute e mantém credenciais fora do LLM.
    from plugins.bridge import attach_plugin_registry
    attach_plugin_registry(registry, permissions)

    return registry
