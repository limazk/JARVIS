"""Helpers seguros para plugins CLI/HTTP."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from plugins.base import PluginResult, PluginStatus


def command_status(executable: str) -> PluginStatus:
    path = shutil.which(executable)
    return PluginStatus(bool(path), path or f"{executable} não encontrado no PATH")


def run_command(
    args: list[str],
    *,
    cwd: str | None = None,
    timeout: int = 120,
    max_output: int = 12000,
) -> PluginResult:
    try:
        result = subprocess.run(
            args,
            cwd=str(Path(cwd).expanduser()) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return PluginResult(False, f"Executável não encontrado: {args[0]}")
    except subprocess.TimeoutExpired:
        return PluginResult(False, f"Comando excedeu {timeout}s.")
    except Exception as exc:
        return PluginResult(False, f"Falha ao executar comando: {exc}")

    output = ((result.stdout or "") + (result.stderr or "")).strip()[:max_output]
    return PluginResult(
        result.returncode == 0,
        output or ("Comando concluído." if result.returncode == 0 else "Comando falhou."),
        {"returncode": result.returncode},
    )


def env_status(*keys: str, detail: str = "") -> PluginStatus:
    missing = [key for key in keys if not os.getenv(key, "").strip()]
    if missing:
        return PluginStatus(False, "faltando " + ", ".join(missing))
    return PluginStatus(True, detail or "configurado")


def request_json(
    method: str,
    url: str,
    *,
    headers: dict | None = None,
    params: dict | None = None,
    json_body: dict | None = None,
    data: dict | None = None,
    timeout: int = 30,
) -> PluginResult:
    try:
        import requests
        response = requests.request(
            method,
            url,
            headers=headers,
            params=params,
            json=json_body,
            data=data,
            timeout=timeout,
        )
    except Exception as exc:
        return PluginResult(False, f"Erro de rede: {exc}")

    try:
        payload = response.json()
    except Exception:
        payload = {"text": response.text[:12000]}

    if not response.ok:
        return PluginResult(
            False,
            f"HTTP {response.status_code}: {str(payload)[:1000]}",
            {"status_code": response.status_code, "response": payload},
        )

    return PluginResult(
        True,
        "Requisição concluída.",
        {"status_code": response.status_code, "response": payload},
    )
