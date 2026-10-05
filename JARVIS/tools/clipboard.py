"""
Área de transferência — seção 19 do spec.

Usa `pyperclip`. Importante: o Jarvis nunca persiste o conteúdo da
área de transferência no banco de dados (poderia conter senhas ou
dados sensíveis) — ele só lê/escreve o clipboard do sistema, em
memória, na hora.
"""
from __future__ import annotations

from core.permissions import RiskLevel
from tools.base import Tool, ToolResult


def get_clipboard(**_: object) -> ToolResult:
    try:
        import pyperclip

        content = pyperclip.paste()
    except Exception as exc:
        return ToolResult(success=False, message=f"Não consegui ler a área de transferência: {exc}")

    if not content:
        return ToolResult(success=True, message="Sua área de transferência está vazia.")
    preview = content if len(content) <= 200 else content[:200] + "..."
    return ToolResult(success=True, message=f"Você copiou: {preview}", data={"content": content})


def set_clipboard(text: str, **_: object) -> ToolResult:
    try:
        import pyperclip

        pyperclip.copy(text)
        return ToolResult(success=True, message="Copiado.")
    except Exception as exc:
        return ToolResult(success=False, message=f"Não consegui copiar: {exc}")


def clear_clipboard(**_: object) -> ToolResult:
    try:
        import pyperclip

        pyperclip.copy("")
        return ToolResult(success=True, message="Área de transferência limpa.")
    except Exception as exc:
        return ToolResult(success=False, message=f"Não consegui limpar a área de transferência: {exc}")


def register(registry) -> None:
    registry.register(Tool(
        name="get_clipboard",
        description="Lê o conteúdo atual da área de transferência.",
        parameters={"type": "object", "properties": {}},
        risk_level=RiskLevel.LOW,
        handler=get_clipboard,
    ))
    registry.register(Tool(
        name="set_clipboard",
        description="Copia um texto para a área de transferência.",
        parameters={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        risk_level=RiskLevel.LOW,
        handler=set_clipboard,
    ))
    registry.register(Tool(
        name="clear_clipboard",
        description="Limpa a área de transferência.",
        parameters={"type": "object", "properties": {}},
        risk_level=RiskLevel.LOW,
        handler=clear_clipboard,
    ))
