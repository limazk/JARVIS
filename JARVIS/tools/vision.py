"""
Visão computacional / OCR — item de roadmap (seção 48) adiantado
porque não depende de nenhuma conta externa, só de bibliotecas.

read_screen_text(): tira um print e extrai o texto visível nele via
OCR (Tesseract, através do pytesseract). Isso permite coisas como
"Jarvis, o que está escrito nessa janela?" ou "leia essa mensagem
de erro pra mim".

IMPORTANTE — requisito extra fora do pip: o Tesseract OCR é um
programa (não uma lib Python) que precisa estar instalado no
Windows separadamente:
    https://github.com/UB-Mannheim/tesseract/wiki
Depois de instalar, se o Jarvis não achar o executável sozinho,
defina o caminho em TESSERACT_CMD no .env (ex.:
"C:\\Program Files\\Tesseract-OCR\\tesseract.exe").
"""
from __future__ import annotations

import os

from core.permissions import RiskLevel
from tools.base import Tool, ToolResult


def _configure_tesseract() -> None:
    import pytesseract

    custom_path = os.getenv("TESSERACT_CMD", "").strip()
    if custom_path:
        pytesseract.pytesseract.tesseract_cmd = custom_path


def read_screen_text(**_: object) -> ToolResult:
    try:
        import pytesseract
        from PIL import ImageGrab
    except ImportError as exc:
        return ToolResult(
            success=False,
            message=f"Faltam bibliotecas para OCR ({exc}). Rode: pip install pillow pytesseract",
        )

    try:
        _configure_tesseract()
        screenshot = ImageGrab.grab()
        text = pytesseract.image_to_string(screenshot, lang="por+eng").strip()
    except Exception as exc:
        return ToolResult(
            success=False,
            message=(
                f"Não consegui ler o texto da tela ({exc}). Verifique se o programa Tesseract OCR "
                "está instalado (https://github.com/UB-Mannheim/tesseract/wiki) e, se necessário, "
                "defina TESSERACT_CMD no .env."
            ),
        )

    if not text:
        return ToolResult(success=True, message="Não encontrei nenhum texto legível na tela agora.")

    preview = text if len(text) <= 600 else text[:600] + "..."
    return ToolResult(success=True, message=f"Texto encontrado na tela:\n{preview}", data={"text": text})


def read_image_text(image_path: str, **_: object) -> ToolResult:
    try:
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        return ToolResult(
            success=False,
            message=f"Faltam bibliotecas para OCR ({exc}). Rode: pip install pillow pytesseract",
        )

    try:
        _configure_tesseract()
        image = Image.open(image_path)
        text = pytesseract.image_to_string(image, lang="por+eng").strip()
    except FileNotFoundError:
        return ToolResult(success=False, message=f"Não achei o arquivo de imagem '{image_path}'.")
    except Exception as exc:
        return ToolResult(success=False, message=f"Não consegui ler o texto da imagem: {exc}")

    if not text:
        return ToolResult(success=True, message="Não encontrei nenhum texto legível nessa imagem.")
    preview = text if len(text) <= 600 else text[:600] + "..."
    return ToolResult(success=True, message=f"Texto encontrado na imagem:\n{preview}", data={"text": text})


def register(registry) -> None:
    registry.register(Tool(
        name="read_screen_text",
        description="Lê (via OCR) o texto visível na tela agora — útil para 'o que está escrito nessa janela'.",
        parameters={"type": "object", "properties": {}},
        risk_level=RiskLevel.LOW,
        handler=read_screen_text,
    ))
    registry.register(Tool(
        name="read_image_text",
        description="Lê (via OCR) o texto contido em um arquivo de imagem, dado o caminho.",
        parameters={"type": "object", "properties": {"image_path": {"type": "string"}}, "required": ["image_path"]},
        risk_level=RiskLevel.LOW,
        handler=read_image_text,
    ))
