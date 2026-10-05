"""
Definição base de uma ferramenta (Tool) do Jarvis — seção 31 do spec.

Toda ferramenta é uma instância desta classe: tem nome, descrição
(usada pelo LLM para decidir quando chamá-la), o schema de
parâmetros, o nível de risco (ligado ao PermissionManager) e um
handler, que SEMPRE devolve um ToolResult padronizado.

Importante: o modelo de IA nunca "finge" que uma ação aconteceu — a
resposta só é considerada bem-sucedida depois que o handler
realmente executa e devolve success=True.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from core.permissions import RiskLevel


@dataclass
class ToolResult:
    success: bool
    message: str
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"success": self.success, "message": self.message, "data": self.data}


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict  # JSON schema simplificado, usado no tool-calling do LLM
    risk_level: RiskLevel
    handler: Callable[..., ToolResult]
    # Texto humano mostrado na confirmação. Pode usar {param} com os kwargs recebidos.
    confirmation_template: Optional[str] = None

    def describe_action(self, **kwargs: Any) -> str:
        if self.confirmation_template:
            try:
                return self.confirmation_template.format(**kwargs)
            except Exception:
                pass
        return f"{self.name}({kwargs})"

    def execute(self, **kwargs: Any) -> ToolResult:
        try:
            return self.handler(**kwargs)
        except Exception as exc:  # uma tool nunca pode derrubar o Jarvis (seção 42)
            return ToolResult(success=False, message=f"Erro ao executar '{self.name}': {exc}")
