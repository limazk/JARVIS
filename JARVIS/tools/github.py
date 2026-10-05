"""
Integração com Git/GitHub — seção 25 do spec, ampliada na ETAPA de
integrações.

Duas camadas:
  1) `git` CLI via subprocess — não exige token, funciona em
     qualquer repositório local (status, push).
  2) API REST do GitHub via `requests` + um Personal Access Token
     (GITHUB_TOKEN no .env) — permite listar repositórios, ver
     detalhes e abrir issues sem precisar estar dentro de uma pasta
     de repositório clonada.

Como gerar o token (grátis, leva ~1 minuto):
    GitHub → Settings → Developer settings → Personal access tokens
    → Tokens (classic) → Generate new token
    Escopos mínimos: "repo" (para issues) e "read:user".
Cole o valor em GITHUB_TOKEN no .env. Sem o token, git_status/
git_push/open_github continuam funcionando normalmente — só as
funções de API (list_my_repos, repo_info, create_issue) precisam
dele.
"""
from __future__ import annotations

import subprocess
import webbrowser
from pathlib import Path
from typing import Optional

from config.settings import settings
from core.permissions import PermissionDenied, PermissionManager, RiskLevel
from tools.base import Tool, ToolResult

_API_BASE = "https://api.github.com"


def _run_git(args: list[str], cwd: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=30)
        output = ((result.stdout or "") + (result.stderr or "")).strip()
        return result.returncode == 0, output
    except FileNotFoundError:
        return False, "Git não está instalado ou não está no PATH."
    except Exception as exc:
        return False, str(exc)


def git_status(project_path: str = ".", **_: object) -> ToolResult:
    path = str(Path(project_path).expanduser())
    ok, output = _run_git(["status", "-s", "-b"], cwd=path)
    if not ok:
        return ToolResult(success=False, message=f"Não consegui checar o status do git: {output}")
    if output.count("\n") <= 0 and "..." not in output:
        return ToolResult(success=True, message=f"Repositório limpo. ({output})")
    return ToolResult(success=True, message=f"Status do git:\n{output}")


def open_github(profile_or_repo: str = "", **_: object) -> ToolResult:
    url = "https://github.com" if not profile_or_repo else f"https://github.com/{profile_or_repo}"
    try:
        webbrowser.open(url)
        return ToolResult(success=True, message="Abrindo o GitHub.")
    except Exception as exc:
        return ToolResult(success=False, message=f"Não consegui abrir o navegador: {exc}")


def _github_api_headers() -> Optional[dict]:
    if not settings.github_token:
        return None
    return {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def list_my_repos(**_: object) -> ToolResult:
    headers = _github_api_headers()
    if headers is None:
        return ToolResult(
            success=False,
            message="Preciso de um GITHUB_TOKEN no .env para listar seus repositórios (veja o topo de tools/github.py).",
        )
    try:
        import requests

        resp = requests.get(
            f"{_API_BASE}/user/repos", headers=headers,
            params={"sort": "updated", "per_page": 10}, timeout=15,
        )
        resp.raise_for_status()
        repos = resp.json()
    except Exception as exc:
        return ToolResult(success=False, message=f"Não consegui consultar o GitHub: {exc}")

    if not repos:
        return ToolResult(success=True, message="Você não tem repositórios (ou o token não tem permissão pra vê-los).")

    listed = "\n".join(f"- {r['full_name']} ({'privado' if r['private'] else 'público'})" for r in repos)
    return ToolResult(success=True, message=f"Seus repositórios mais recentes:\n{listed}", data={"repos": repos})


def repo_info(repo: str, **_: object) -> ToolResult:
    """`repo` no formato "usuario/repositorio"."""
    headers = _github_api_headers()
    try:
        import requests

        resp = requests.get(f"{_API_BASE}/repos/{repo}", headers=headers or {}, timeout=15)
        if resp.status_code == 404:
            return ToolResult(success=False, message=f"Não achei o repositório '{repo}'.")
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return ToolResult(success=False, message=f"Não consegui consultar o GitHub: {exc}")

    message = (
        f"{data['full_name']}: {data.get('description') or 'sem descrição'}. "
        f"{data['stargazers_count']} estrelas, {data['open_issues_count']} issues abertas, "
        f"linguagem principal: {data.get('language') or 'N/A'}."
    )
    return ToolResult(success=True, message=message, data=data)


def register(registry, permissions: Optional[PermissionManager] = None) -> None:
    registry.register(Tool(
        name="git_status",
        description="Mostra o status do repositório git (branch, alterações pendentes) na pasta do projeto atual.",
        parameters={"type": "object", "properties": {"project_path": {"type": "string"}}},
        risk_level=RiskLevel.LOW,
        handler=git_status,
    ))
    registry.register(Tool(
        name="open_github",
        description="Abre o GitHub no navegador (opcionalmente um perfil/repositório específico).",
        parameters={"type": "object", "properties": {"profile_or_repo": {"type": "string"}}},
        risk_level=RiskLevel.LOW,
        handler=open_github,
    ))
    registry.register(Tool(
        name="list_my_repos",
        description="Lista os repositórios do GitHub do usuário (requer GITHUB_TOKEN configurado).",
        parameters={"type": "object", "properties": {}},
        risk_level=RiskLevel.LOW,
        handler=list_my_repos,
    ))
    registry.register(Tool(
        name="repo_info",
        description="Mostra informações de um repositório do GitHub (estrelas, issues, linguagem). Formato: usuario/repositorio.",
        parameters={"type": "object", "properties": {"repo": {"type": "string"}}, "required": ["repo"]},
        risk_level=RiskLevel.LOW,
        handler=repo_info,
    ))

    def git_push_handler(project_path: str = ".", **_: object) -> ToolResult:
        path = str(Path(project_path).expanduser())
        if permissions is not None:
            try:
                permissions.check("git_push", RiskLevel.HIGH, f"Fazer git push em {path}")
            except PermissionDenied as exc:
                return ToolResult(success=False, message=str(exc))
        ok, output = _run_git(["push"], cwd=path)
        return ToolResult(success=ok, message=output or ("Push feito." if ok else "Push falhou."))

    registry.register(Tool(
        name="git_push",
        description="Envia commits para o repositório remoto (git push). Sempre exige confirmação.",
        parameters={"type": "object", "properties": {"project_path": {"type": "string"}}},
        risk_level=RiskLevel.HIGH,
        handler=git_push_handler,
        confirmation_template="Fazer git push em {project_path}",
    ))

    def create_issue_handler(repo: str, title: str, body: str = "", **_: object) -> ToolResult:
        headers = _github_api_headers()
        if headers is None:
            return ToolResult(success=False, message="Preciso de um GITHUB_TOKEN no .env para criar issues.")
        if permissions is not None:
            try:
                permissions.check("create_issue", RiskLevel.MEDIUM, f"Criar issue em {repo}: '{title}'")
            except PermissionDenied as exc:
                return ToolResult(success=False, message=str(exc))
        try:
            import requests

            resp = requests.post(
                f"{_API_BASE}/repos/{repo}/issues", headers=headers,
                json={"title": title, "body": body}, timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            return ToolResult(success=False, message=f"Não consegui criar a issue: {exc}")
        return ToolResult(success=True, message=f"Issue criada: {data['html_url']}", data=data)

    registry.register(Tool(
        name="create_issue",
        description="Cria uma issue em um repositório do GitHub (formato usuario/repositorio). Exige confirmação.",
        parameters={
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "title": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["repo", "title"],
        },
        risk_level=RiskLevel.MEDIUM,
        handler=create_issue_handler,
        confirmation_template="Criar issue em {repo}: '{title}'",
    ))
