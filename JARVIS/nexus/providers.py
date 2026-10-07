"""Providers do NEXUS.

Há dois tipos:
- CLI: agentes que podem trabalhar diretamente no terminal/repositório.
- API: IAs online baratas/rápidas para roteamento, planejamento, revisão
  e respostas. Todas usam Chat Completions compatível com OpenAI.

Nenhuma chave é versionada; tudo vem do .env.
"""
from __future__ import annotations

import os
import queue
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Callable

from config.settings import settings


@dataclass(frozen=True)
class Provider:
    key: str
    label: str
    transport: str
    model: str
    available: bool
    endpoint: str = ""
    capabilities: tuple[str, ...] = ()
    routing_only: bool = False


@dataclass(frozen=True)
class ProviderRun:
    ok: bool
    text: str
    provider: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    status_code: int = 0


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _api_available(key: str, *, extra: bool = True) -> bool:
    return bool(_env(key)) and extra


def discover() -> dict[str, Provider]:
    """Descobre CLIs instalados e APIs configuradas, sem fazer requests."""
    cf_token = _env("CLOUDFLARE_API_TOKEN") or _env("CLOUDFLARE_AUTH_TOKEN")
    cf_account = _env("CLOUDFLARE_ACCOUNT_ID")

    result = {
        # Agentes de terminal: adequados para alteração real de arquivos.
        "codex": Provider(
            "codex", "Codex", "cli", "Codex CLI",
            shutil.which("codex") is not None,
            capabilities=("code", "edit", "test", "terminal"),
        ),
        "claude": Provider(
            "claude", "Claude", "cli", "Claude CLI",
            shutil.which("claude") is not None,
            capabilities=("code", "edit", "reason", "terminal"),
        ),
        "gemini_cli": Provider(
            "gemini_cli", "Gemini CLI", "cli", "Gemini CLI",
            shutil.which("gemini") is not None,
            capabilities=("code", "edit", "terminal"),
        ),
        "ollama": Provider(
            "ollama", "Ollama", "cli", settings.local_llm_model,
            shutil.which("ollama") is not None,
            capabilities=("local", "reason", "code"),
        ),

        # Routers online: SOMENTE identificam/roteiam; nunca executam a tarefa final.
        "grok": Provider(
            "grok", "Grok", "api",
            _env("NEXUS_GROK_MODEL", "grok-4.7"),
            _api_available("XAI_API_KEY"),
            "https://api.x.ai/v1",
            ("router", "classification"),
            True,
        ),
        "mistral": Provider(
            "mistral", "Mistral Router", "api",
            _env("MISTRAL_MODEL", "ministral-3b-latest"),
            _api_available("MISTRAL_API_KEY"),
            "https://api.mistral.ai/v1",
            ("router", "classification"),
            True,
        ),

        # Workers online: funcionalidades executoras/analíticas, como os demais agentes.
        "gemini": Provider(
            "gemini", "Gemini", "api",
            _env("NEXUS_GEMINI_MODEL", "gemini-3.8-flash"),
            bool(settings.gemini_api_key),
            "https://generativelanguage.googleapis.com/v1beta/openai",
            ("reason", "review", "general"),
        ),
        "groq": Provider(
            "groq", "Groq", "api",
            _env("NEXUS_GROQ_MODEL", "openai/gpt-oss-20b"),
            bool(settings.groq_api_key),
            "https://api.groq.com/openai/v1",
            ("fast", "reason", "review", "general"),
        ),
        "openrouter": Provider(
            "openrouter", "OpenRouter", "api",
            _env("OPENROUTER_MODEL", "openrouter/free"),
            _api_available("OPENROUTER_API_KEY"),
            "https://openrouter.ai/api/v1",
            ("fallback", "general", "review", "reason"),
        ),
        "cloudflare": Provider(
            "cloudflare", "Cloudflare AI", "api",
            _env("CLOUDFLARE_MODEL", "@cf/openai/gpt-oss-20b"),
            bool(cf_token and cf_account),
            (
                f"https://api.cloudflare.com/client/v4/accounts/{cf_account}/ai/v1"
                if cf_account else ""
            ),
            ("fast", "general", "reason"),
        ),
        "together": Provider(
            "together", "Together AI", "api",
            _env("TOGETHER_MODEL", "Prism-ML/Ternary-Bonsai-27B"),
            _api_available("TOGETHER_API_KEY"),
            "https://api.together.ai/v1",
            ("general", "review", "reason", "open_models"),
        ),
        "cerebras": Provider(
            "cerebras", "Cerebras", "api",
            _env("CEREBRAS_MODEL", "zai-glm-4.7"),
            _api_available("CEREBRAS_API_KEY"),
            "https://api.cerebras.ai/v1",
            ("fast", "reason", "code_review", "agentic"),
        ),
    }
    return result


def availability_map() -> dict[str, bool]:
    out = {key: provider.available for key, provider in discover().items()}
    out["jarvis"] = True
    return out


def _commands(provider: str, prompt: str) -> list[list[str]]:
    if provider == "claude":
        return [["claude", "-p", prompt], ["claude", "--print", prompt]]
    if provider == "codex":
        return [
            ["codex", "exec", "--skip-git-repo-check", prompt],
            ["codex", "exec", prompt],
        ]
    if provider == "gemini_cli":
        return [["gemini", "-p", prompt], ["gemini", "--prompt", prompt]]
    if provider == "ollama":
        return [["ollama", "run", settings.local_llm_model, prompt]]
    raise ValueError(f"Provider CLI não suportado: {provider}")


def run_cli(
    provider: str,
    prompt: str,
    *,
    timeout: int = 300,
    max_output_chars: int = 50000,
    on_line: Callable[[str], None] | None = None,
) -> ProviderRun:
    """Executa um worker CLI e mantém a TUI responsiva."""
    last_error = ""
    for command in _commands(provider, prompt):
        try:
            proc = subprocess.Popen(
                command,
                cwd=str(settings.base_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError:
            return ProviderRun(False, f"{provider}: executável não encontrado.", provider, status_code=127)
        except OSError as exc:
            last_error = str(exc)
            continue

        lines: list[str] = []
        line_queue: queue.Queue[str | None] = queue.Queue()

        def _reader() -> None:
            assert proc.stdout is not None
            try:
                for line in proc.stdout:
                    line_queue.put(line.rstrip("\n"))
            finally:
                line_queue.put(None)

        threading.Thread(target=_reader, daemon=True).start()
        started = time.monotonic()
        reader_done = False

        while True:
            if time.monotonic() - started > timeout:
                proc.kill()
                return ProviderRun(False, f"{provider}: timeout após {timeout}s.", provider, status_code=124)

            try:
                item = line_queue.get(timeout=0.10)
                if item is None:
                    reader_done = True
                elif item:
                    lines.append(item)
                    if on_line is not None:
                        on_line(item)
            except queue.Empty:
                pass

            if sum(len(line) for line in lines) > max_output_chars:
                proc.kill()
                lines.append("[saída truncada pelo NEXUS]")
                return ProviderRun(True, "\n".join(lines), provider)

            if proc.poll() is not None and reader_done:
                break

        code = proc.wait()
        output = "\n".join(lines).strip()
        if code == 0:
            return ProviderRun(True, output, provider)
        last_error = output or f"{provider}: código de saída {code}."

    return ProviderRun(False, last_error or f"{provider}: falha desconhecida.", provider, status_code=1)


def _api_key(provider: str) -> str:
    if provider == "grok":
        return _env("XAI_API_KEY")
    if provider == "gemini":
        return settings.gemini_api_key
    if provider == "groq":
        return settings.groq_api_key
    if provider == "openrouter":
        return _env("OPENROUTER_API_KEY")
    if provider == "mistral":
        return _env("MISTRAL_API_KEY")
    if provider == "cloudflare":
        return _env("CLOUDFLARE_API_TOKEN") or _env("CLOUDFLARE_AUTH_TOKEN")
    if provider == "together":
        return _env("TOGETHER_API_KEY")
    if provider == "cerebras":
        return _env("CEREBRAS_API_KEY")
    return ""


def run_api_provider(
    provider: str,
    prompt: str,
    *,
    max_tokens: int = 1200,
    router_mode: bool = False,
) -> ProviderRun:
    """Executa uma API compatível com Chat Completions.

    No router, a saída é propositalmente minúscula para reduzir tokens.
    """
    providers = discover()
    spec = providers.get(provider)
    if spec is None or spec.transport != "api":
        return ProviderRun(False, f"{provider}: provider API inválido.", provider, status_code=400)
    if not spec.available:
        return ProviderRun(False, f"{provider}: API não configurada.", provider, status_code=401)

    try:
        import requests
    except ImportError:
        return ProviderRun(False, "Pacote requests não instalado.", provider, status_code=500)

    api_key = _api_key(provider)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if provider == "openrouter":
        headers["X-Title"] = "NEXUS"
        referer = _env("OPENROUTER_HTTP_REFERER")
        if referer:
            headers["HTTP-Referer"] = referer

    system_prompt = (
        "Você é o roteador econômico do NEXUS. Responda somente no formato pedido, "
        "sem explicações extras."
        if router_mode
        else (
            "Você é um worker do NEXUS integrado ao JARVIS. Responda de forma objetiva. "
            "Não afirme que alterou arquivos ou executou comandos se você só recebeu texto."
        )
    )
    payload: dict = {
        "model": spec.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }

    # Limites curtos são a principal defesa contra desperdício.
    if provider == "grok":
        payload["max_completion_tokens"] = max_tokens
        payload["temperature"] = 0.1 if router_mode else 0.3
        if router_mode:
            payload["reasoning_effort"] = "low"
    elif provider == "cerebras":
        payload["max_completion_tokens"] = max_tokens
        payload["temperature"] = 0.8 if router_mode else 0.9
        if router_mode:
            payload["reasoning_effort"] = "none"
    else:
        payload["max_tokens"] = max_tokens
        payload["temperature"] = 0.1 if router_mode else 0.3

    timeout = max(5, int(_env("NEXUS_API_TIMEOUT", "120") or "120"))
    try:
        response = requests.post(
            f"{spec.endpoint.rstrip('/')}/chat/completions",
            headers=headers,
            json=payload,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        return ProviderRun(False, f"{provider}: erro de rede ({exc}).", provider, status_code=503)

    if not response.ok:
        detail = response.text.replace("\n", " ")[:500]
        return ProviderRun(
            False,
            f"{provider}: HTTP {response.status_code} — {detail}",
            provider,
            status_code=response.status_code,
        )

    try:
        data = response.json()
        message = data["choices"][0]["message"]
        text = message.get("content") or ""
        usage = data.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens))
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        return ProviderRun(False, f"{provider}: resposta inválida ({exc}).", provider, status_code=502)

    return ProviderRun(
        True,
        str(text).strip(),
        provider,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        status_code=response.status_code,
    )


def run_provider(
    provider: str,
    prompt: str,
    *,
    timeout: int = 300,
    max_output_chars: int = 50000,
    max_api_tokens: int = 1200,
    on_line: Callable[[str], None] | None = None,
) -> ProviderRun:
    spec = discover().get(provider)
    if spec is None:
        return ProviderRun(False, f"Provider desconhecido: {provider}", provider, status_code=404)
    if spec.routing_only:
        return ProviderRun(
            False,
            f"{provider}: reservado ao roteamento e não pode executar a tarefa final.",
            provider,
            status_code=409,
        )
    if spec.transport == "cli":
        return run_cli(
            provider,
            prompt,
            timeout=timeout,
            max_output_chars=max_output_chars,
            on_line=on_line,
        )
    run = run_api_provider(provider, prompt, max_tokens=max_api_tokens)
    if run.ok and on_line is not None and run.text:
        on_line(run.text)
    return run


def worker_prompt(user_prompt: str, memories: list[str], plugin_context: str = "") -> str:
    """Monta contexto mínimo: nunca envia o histórico inteiro."""
    context = ""
    if memories:
        compact = [fact[:280] for fact in memories[:5]]
        context = (
            "\n\nContexto relevante da memória do JARVIS:\n"
            + "\n".join(f"- {fact}" for fact in compact)
        )
    max_task_chars = max(1000, int(_env("NEXUS_WORKER_MAX_INPUT_CHARS", "12000") or "12000"))
    task = user_prompt[:max_task_chars]
    return (
        "Execute ou analise esta tarefa. Seja objetivo e economize tokens. "
        "Se você não possui acesso ao terminal, entregue instruções/patches e não finja execução. "
        f"Raiz do projeto quando houver acesso local: {settings.base_dir}.\n\n"
        f"Tarefa:\n{task}{context}"
        + (f"\n\n{plugin_context}" if plugin_context else "")
    )
