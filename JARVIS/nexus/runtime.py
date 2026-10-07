"""Runtime do NEXUS integrado ao núcleo real do JARVIS."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Callable

from config.settings import settings
from core.agent import JarvisAgent
from memory import memory as long_term_memory
from memory.database import get_connection, log_activity
from nexus.providers import availability_map, discover, run_cli, worker_prompt
from nexus.router import choose_provider

EventCallback = Callable[[str, str, str, str], None]
OutputCallback = Callable[[str], None]
ConfirmCallback = Callable[[str], bool]


@dataclass
class RunResult:
    ok: bool
    provider: str
    kind: str
    text: str
    elapsed: float


class NexusHistory:
    """Histórico do NEXUS no MESMO banco SQLite do JARVIS."""

    def __init__(self) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS nexus_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prompt TEXT NOT NULL,
                    status TEXT NOT NULL,
                    provider TEXT NOT NULL DEFAULT '',
                    kind TEXT NOT NULL DEFAULT '',
                    elapsed REAL NOT NULL DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def start(self, prompt: str) -> int:
        with get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO nexus_jobs(prompt,status) VALUES(?,?)",
                (prompt, "em andamento"),
            )
            return int(cur.lastrowid)

    def finish(self, job_id: int, status: str, provider: str, kind: str, elapsed: float) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE nexus_jobs SET status=?,provider=?,kind=?,elapsed=? WHERE id=?",
                (status, provider, kind, elapsed, job_id),
            )

    def recent(self, limit: int = 8) -> list[dict]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id,prompt,status,provider,kind,elapsed,created_at
                FROM nexus_jobs
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]


class NexusRuntime:
    """Ponte JARVIS ↔ NEXUS.

    - JARVIS continua responsável por tools, memória e permissões.
    - Workers externos são usados apenas quando o roteador julga vantajoso.
    - Se um worker externo falha, o JARVIS interno assume automaticamente.
    """

    def __init__(
        self,
        *,
        confirm_callback: ConfirmCallback | None = None,
        on_event: EventCallback | None = None,
        on_output: OutputCallback | None = None,
        demo: bool = False,
    ) -> None:
        self.on_event = on_event
        self.on_output = on_output
        self.demo = demo
        self.timeout = int(os.getenv("NEXUS_PROVIDER_TIMEOUT", "300"))
        self.max_output = int(os.getenv("NEXUS_MAX_OUTPUT", "50000"))
        self.history = NexusHistory()
        self._providers = discover()
        self.jarvis = JarvisAgent(
            confirm_callback=confirm_callback,
            on_reminder_due=lambda message: self._emit("jarvis", "lembrete", message, "jarvis"),
            start_reminder_scheduler=False,
        )

    def _emit(self, actor: str, state: str, message: str = "", provider: str = "") -> None:
        if self.on_event is not None:
            self.on_event(actor, state, message, provider)

    def _output(self, line: str) -> None:
        if self.on_output is not None and line:
            self.on_output(line)

    def refresh(self) -> None:
        self._providers = discover()

    @property
    def providers(self):
        return self._providers

    def provider_status(self) -> dict[str, bool]:
        status = {key: p.available for key, p in self._providers.items()}
        status["jarvis"] = True
        return status

    def recent_jobs(self, limit: int = 8) -> list[dict]:
        return self.history.recent(limit)

    def execute(self, prompt: str) -> RunResult:
        started = time.monotonic()
        job_id = self.history.start(prompt)
        provider = "jarvis"
        kind = "general"
        status = "erro"

        try:
            self._emit("planner", "planejando", "analisando objetivo", "")
            time.sleep(0.08)

            self.refresh()
            provider, kind = choose_provider(prompt, self.provider_status())
            self._emit("router", "roteando", f"classe: {kind}", provider)
            log_activity(f"NEXUS roteou '{prompt[:80]}' para {provider}")

            if self.demo:
                return self._run_demo(job_id, prompt, provider, kind, started)

            if provider == "jarvis":
                self._emit("jarvis", "executando", "usando memória + tools do JARVIS", "jarvis")
                text = self.jarvis.process(prompt, response_mode="text")
                self._output(text)
            else:
                memories = long_term_memory.recall_relevant(prompt, limit=5)
                delegated_prompt = worker_prompt(prompt, memories)
                self._emit("worker", "executando", f"worker {provider}", provider)

                code, text = run_cli(
                    provider,
                    delegated_prompt,
                    timeout=self.timeout,
                    max_output_chars=self.max_output,
                    on_line=self._output,
                )
                if code != 0:
                    self._emit(
                        "router",
                        "fallback",
                        f"{provider} falhou; assumindo com JARVIS",
                        "jarvis",
                    )
                    fallback_reason = text[-500:] if text else "sem saída"
                    self._output(f"[NEXUS] {provider} falhou: {fallback_reason}")
                    text = self.jarvis.process(prompt, response_mode="text")
                    self._output(text)
                    provider = f"{provider}→jarvis"

            self._emit("reviewer", "revisando", "validando entrega", provider)
            if not text.strip():
                text = "O worker terminou sem retornar conteúdo."
            elapsed = time.monotonic() - started
            status = "concluído"
            self.history.finish(job_id, status, provider, kind, elapsed)
            log_activity(f"NEXUS concluiu tarefa via {provider} em {elapsed:.1f}s")
            self._emit("reviewer", "concluído", "entrega pronta", provider)
            return RunResult(True, provider, kind, text, elapsed)
        except Exception as exc:
            elapsed = time.monotonic() - started
            error = f"NEXUS não conseguiu concluir a tarefa: {exc}"
            self._output(error)
            self.history.finish(job_id, "erro", provider, kind, elapsed)
            self._emit("nexus", "erro", str(exc), provider)
            return RunResult(False, provider, kind, error, elapsed)

    def _run_demo(
        self,
        job_id: int,
        prompt: str,
        provider: str,
        kind: str,
        started: float,
    ) -> RunResult:
        stages = (
            ("planner", "planejando", "quebrando a tarefa em etapas"),
            ("router", "roteando", f"selecionado: {provider}"),
            ("worker", "executando", "executando subtarefa principal"),
            ("reviewer", "revisando", "validando resultado"),
        )
        for actor, state, message in stages:
            self._emit(actor, state, message, provider)
            self._output(f"[DEMO] {actor}: {message}")
            time.sleep(0.18)
        text = (
            "Modo DEMO concluído. A integração JARVIS ↔ NEXUS está carregada; "
            "nenhum provider externo foi chamado."
        )
        self._output(text)
        elapsed = time.monotonic() - started
        self.history.finish(job_id, "concluído", f"demo:{provider}", kind, elapsed)
        self._emit("reviewer", "concluído", "demo finalizada", provider)
        return RunResult(True, f"demo:{provider}", kind, text, elapsed)

    def shutdown(self) -> None:
        self.jarvis.shutdown()
