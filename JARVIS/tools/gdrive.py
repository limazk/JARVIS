"""
Google Drive — buscar arquivos direto do Jarvis (só leitura, de
propósito — nada aqui apaga/sobrescreve nada no Drive). Parte da
integração Google (item do roadmap "Gmail/Calendar/Drive"); mesma
autenticação/configuração do Gmail (tools/google_auth.py).
"""
from __future__ import annotations

from core.permissions import RiskLevel
from tools.base import Tool, ToolResult
from tools.google_auth import get_google_service, no_google_credentials_result


def search_drive_files(query: str, limit: int = 5, **_: object) -> ToolResult:
    service = get_google_service("drive", "v3")
    if service is None:
        return no_google_credentials_result()
    safe_query = query.replace("'", "\\'")
    try:
        resp = (
            service.files()
            .list(
                q=f"name contains '{safe_query}' and trashed = false",
                pageSize=limit,
                fields="files(id, name, webViewLink)",
            )
            .execute()
        )
        files = resp.get("files", [])
        if not files:
            return ToolResult(success=True, message=f"Não achei nenhum arquivo no Drive parecido com '{query}'.")
        lines = [f"- {f['name']}: {f.get('webViewLink', '')}" for f in files]
        return ToolResult(success=True, message="Achei no Drive:\n" + "\n".join(lines))
    except Exception as exc:
        return ToolResult(success=False, message=f"Não consegui consultar o Drive: {exc}")


def register(registry) -> None:
    registry.register(Tool(
        name="search_drive_files",
        description="Busca arquivos no Google Drive do usuário pelo nome (só consulta, não apaga nem altera nada).",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "description": "Padrão 5"},
            },
            "required": ["query"],
        },
        risk_level=RiskLevel.LOW,
        handler=search_drive_files,
    ))
