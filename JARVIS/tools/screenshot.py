"""
Captura de tela — seção 18 do spec.

Salva sempre em Pictures/Jarvis/Screenshots/ com nome baseado em
data/hora, e devolve o caminho salvo. Usa Pillow (ImageGrab), que
funciona nativamente no Windows sem dependências extras do sistema.
"""
from __future__ import annotations

from datetime import datetime

from config.settings import settings
from core.permissions import RiskLevel
from tools.base import Tool, ToolResult


def take_screenshot(**_: object) -> ToolResult:
    try:
        from PIL import ImageGrab
    except ImportError:
        return ToolResult(success=False, message="A biblioteca Pillow não está instalada (pip install pillow).")

    try:
        settings.screenshots_dir.mkdir(parents=True, exist_ok=True)
        filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        path = settings.screenshots_dir / filename
        image = ImageGrab.grab()
        image.save(path)
        return ToolResult(success=True, message=f"Print salvo em {path}.", data={"path": str(path)})
    except Exception as exc:
        return ToolResult(success=False, message=f"Não consegui tirar o print: {exc}")


def register(registry) -> None:
    registry.register(Tool(
        name="take_screenshot",
        description="Tira uma captura de tela e salva em Pictures/Jarvis/Screenshots.",
        parameters={"type": "object", "properties": {}},
        risk_level=RiskLevel.LOW,
        handler=take_screenshot,
    ))
