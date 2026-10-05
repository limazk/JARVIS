"""
Gerenciador de arquivos — seção 17 do spec.

Operações aqui são apenas de leitura/criação (LOW_RISK). Operações
destrutivas (deletar, mover em massa, sobrescrever) estão fora do
escopo deste módulo de propósito — o spec (seção 17 e 28) exige
confirmação explícita para elas, e o protótipo prefere não incluir
uma ferramenta de deleção de arquivos automatizável por voz até que
haja uma camada de confirmação de UI mais robusta que um simples
sim/não no console. Ficará documentado no roadmap.
"""
from __future__ import annotations

from pathlib import Path

from core.permissions import RiskLevel
from tools.base import Tool, ToolResult
from platform_services import get_platform_services

_KNOWN_FOLDERS = {
    "downloads": "Downloads",
    "documentos": "Documents",
    "documents": "Documents",
    "desktop": "Desktop",
    "área de trabalho": "Desktop",
    "area de trabalho": "Desktop",
    "imagens": "Pictures",
    "pictures": "Pictures",
    "vídeos": "Videos",
    "videos": "Videos",
    "músicas": "Music",
    "musicas": "Music",
}


def _resolve_known_folder(name: str) -> Path | None:
    folder = _KNOWN_FOLDERS.get(name.strip().lower())
    if folder is None:
        return None
    return Path.home() / folder


def open_folder(folder: str, **_: object) -> ToolResult:
    path = _resolve_known_folder(folder) or Path(folder).expanduser()
    if not path.exists():
        return ToolResult(success=False, message=f"A pasta '{folder}' não existe ({path}).")

    result = get_platform_services().open_path(path)
    return ToolResult(result.success, f"Abrindo {folder}." if result.success else result.message, result.data)


def create_folder(name: str, parent: str = "", **_: object) -> ToolResult:
    base = _resolve_known_folder(parent) if parent else Path.home() / "Documents"
    base = base or Path.home() / "Documents"
    target = base / name
    try:
        target.mkdir(parents=True, exist_ok=True)
        return ToolResult(success=True, message=f"Pasta '{name}' criada em {target}.", data={"path": str(target)})
    except Exception as exc:
        return ToolResult(success=False, message=f"Não consegui criar a pasta: {exc}")


def find_file(name: str, **_: object) -> ToolResult:
    search_root = Path.home()
    matches: list[str] = []
    try:
        for path in search_root.rglob(f"*{name}*"):
            if path.is_file():
                matches.append(str(path))
            if len(matches) >= 10:
                break
    except (PermissionError, OSError):
        pass

    if not matches:
        return ToolResult(success=False, message=f"Não encontrei nenhum arquivo com '{name}' na sua pasta pessoal.")

    preview = "\n".join(matches[:5])
    return ToolResult(
        success=True,
        message=f"Encontrei {len(matches)} arquivo(s). Os primeiros:\n{preview}",
        data={"matches": matches},
    )


def disk_space(drive: str = "C:\\", **_: object) -> ToolResult:
    import shutil as _shutil

    import platform
    path = drive if platform.system() == "Windows" else "/"
    try:
        usage = _shutil.disk_usage(path)
        free_gb = round(usage.free / (1024**3), 1)
        total_gb = round(usage.total / (1024**3), 1)
        return ToolResult(
            success=True,
            message=f"Você tem {free_gb}GB livres de {total_gb}GB em {path}.",
            data={"free_gb": free_gb, "total_gb": total_gb},
        )
    except Exception as exc:
        return ToolResult(success=False, message=f"Não consegui checar o espaço em disco: {exc}")


def register(registry) -> None:
    registry.register(Tool(
        name="open_folder",
        description="Abre uma pasta no explorador de arquivos (ex.: downloads, documentos, desktop, ou um caminho).",
        parameters={"type": "object", "properties": {"folder": {"type": "string"}}, "required": ["folder"]},
        risk_level=RiskLevel.LOW,
        handler=open_folder,
        confirmation_template="Abrir a pasta {folder}",
    ))
    registry.register(Tool(
        name="create_folder",
        description="Cria uma nova pasta (por padrão dentro de Documentos).",
        parameters={
            "type": "object",
            "properties": {"name": {"type": "string"}, "parent": {"type": "string", "description": "Pasta conhecida onde criar, opcional"}},
            "required": ["name"],
        },
        risk_level=RiskLevel.LOW,
        handler=create_folder,
        confirmation_template="Criar a pasta '{name}'",
    ))
    registry.register(Tool(
        name="find_file",
        description="Procura um arquivo pelo nome (ou parte do nome) na pasta pessoal do usuário.",
        parameters={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        risk_level=RiskLevel.LOW,
        handler=find_file,
    ))
    registry.register(Tool(
        name="disk_space",
        description="Consulta o espaço livre em um disco (ex.: C:).",
        parameters={"type": "object", "properties": {"drive": {"type": "string"}}},
        risk_level=RiskLevel.LOW,
        handler=disk_space,
    ))
