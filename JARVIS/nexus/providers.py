"""Workers externos do NEXUS.

Os CLIs são opcionais. O NEXUS detecta o que existe no computador e
sempre mantém o JARVIS interno como fallback.
"""
from __future__ import annotations

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
    executable: str
    model: str
    available: bool


def discover() -> dict[str, Provider]:
    specs = {
        "claude": ("Claude", "claude", "Claude CLI"),
        "codex": ("Codex", "codex", "Codex CLI"),
        "gemini": ("Gemini", "gemini", "Gemini CLI"),
        "ollama": ("Ollama", "ollama", settings.local_llm_model),
    }
    result: dict[str, Provider] = {}
    for key, (label, executable, model) in specs.items():
        result[key] = Provider(
            key=key,
            label=label,
            executable=executable,
            model=model,
            available=shutil.which(executable) is not None,
        )
    return result


def availability_map() -> dict[str, bool]:
    out = {key: provider.available for key, provider in discover().items()}
    # O JARVIS interno existe mesmo sem LLM remoto: intents locais/tools
    # continuam funcionais e o próprio brain possui fallback configurável.
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
    if provider == "gemini":
        return [["gemini", "-p", prompt], ["gemini", "--prompt", prompt]]
    if provider == "ollama":
        return [["ollama", "run", settings.local_llm_model, prompt]]
    raise ValueError(f"Provider não suportado: {provider}")


def run_cli(
    provider: str,
    prompt: str,
    *,
    timeout: int = 300,
    max_output_chars: int = 50000,
    on_line: Callable[[str], None] | None = None,
) -> tuple[int, str]:
    """Executa um worker CLI com streaming sem bloquear o timeout."""
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
            return 127, f"{provider}: executável não encontrado."
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
                return 124, f"{provider}: timeout após {timeout}s."

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
                return 0, "\n".join(lines)

            if proc.poll() is not None and reader_done:
                break

        code = proc.wait()
        output = "\n".join(lines).strip()
        if code == 0:
            return 0, output
        last_error = output or f"{provider}: código de saída {code}."

    return 1, last_error or f"{provider}: falha desconhecida."


def worker_prompt(user_prompt: str, memories: list[str]) -> str:
    context = ""
    if memories:
        context = (
            "\n\nContexto relevante da memória do JARVIS (use apenas se ajudar):\n"
            + "\n".join(f"- {fact}" for fact in memories)
        )
    return (
        "Você é um worker especialista do NEXUS, orquestrador integrado ao JARVIS. "
        "Execute a tarefa diretamente, seja objetivo, não finja ações que não realizou "
        "e reporte claramente arquivos/comandos alterados quando aplicável. "
        f"Você está trabalhando na raiz do projeto JARVIS: {settings.base_dir}.\n\n"
        f"Tarefa do usuário:\n{user_prompt}{context}"
    )
