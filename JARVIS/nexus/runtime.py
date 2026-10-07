"""Runtime do NEXUS integrado ao núcleo real do JARVIS.

Estratégia de custo:
1) regras locais;
2) verificador online só quando a rota estiver ambígua;
3) uma única IA executora por padrão;
4) fallback para JARVIS sem abrir uma "bancada" de modelos em paralelo.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Callable

from config.settings import settings
from core.agent import JarvisAgent
from memory import memory as long_term_memory
from memory.database import get_connection, log_activity
from plugins.broker import describe_plugins, execute_requests
from nexus.online_router import OnlineRouterResult, verify_route
from nexus.providers import discover, run_provider, worker_prompt
from nexus.router import RoutingDecision, local_route

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
    route_source: str = "local"
    route_confidence: float = 0.0
    router_calls: int = 0
    router_tokens: int = 0
    worker_tokens: int = 0
    api_calls: int = 0


class NexusHistory:
    """Histórico do NEXUS no mesmo SQLite do JARVIS, com métricas de economia."""

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
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(nexus_jobs)").fetchall()}
            for name, sql_type, default in (
                ("route_source", "TEXT", "''"),
                ("route_confidence", "REAL", "0"),
                ("router_calls", "INTEGER", "0"),
                ("router_tokens", "INTEGER", "0"),
                ("worker_tokens", "INTEGER", "0"),
                ("api_calls", "INTEGER", "0"),
            ):
                if name not in columns:
                    conn.execute(
                        f"ALTER TABLE nexus_jobs ADD COLUMN {name} {sql_type} NOT NULL DEFAULT {default}"
                    )

    def start(self, prompt: str) -> int:
        with get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO nexus_jobs(prompt,status) VALUES(?,?)",
                (prompt, "em andamento"),
            )
            return int(cur.lastrowid)

    def finish(self, job_id: int, result: RunResult) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE nexus_jobs
                SET status=?, provider=?, kind=?, elapsed=?,
                    route_source=?, route_confidence=?, router_calls=?,
                    router_tokens=?, worker_tokens=?, api_calls=?
                WHERE id=?
                """,
                (
                    "concluído" if result.ok else "erro",
                    result.provider,
                    result.kind,
                    result.elapsed,
                    result.route_source,
                    result.route_confidence,
                    result.router_calls,
                    result.router_tokens,
                    result.worker_tokens,
                    result.api_calls,
                    job_id,
                ),
            )

    def recent(self, limit: int = 8) -> list[dict]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id,prompt,status,provider,kind,elapsed,created_at,
                       route_source,route_confidence,router_calls,
                       router_tokens,worker_tokens,api_calls
                FROM nexus_jobs
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]


class NexusRuntime:
    """Ponte JARVIS ↔ NEXUS com roteamento econômico."""

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
        self.max_api_tokens = int(os.getenv("NEXUS_WORKER_MAX_OUTPUT_TOKENS", "1200"))
        self.history = NexusHistory()
        self._providers = discover()
        self._route_cache: dict[str, tuple[float, OnlineRouterResult]] = {}
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

    def _cached_verify(
        self,
        prompt: str,
        local: RoutingDecision,
        availability: dict[str, bool],
    ) -> OnlineRouterResult:
        ttl = max(0, int(os.getenv("NEXUS_ROUTER_CACHE_TTL", "1800")))
        key = " ".join(prompt.lower().split())[:2000]
        now = time.monotonic()
        cached = self._route_cache.get(key)
        if cached and cached[0] > now:
            cached_result = cached[1]
            # Cache hit não gasta novos tokens/chamadas.
            decision = RoutingDecision(
                provider=cached_result.decision.provider,
                kind=cached_result.decision.kind,
                confidence=cached_result.decision.confidence,
                source="router_cache",
                reason=cached_result.decision.reason,
                verifier=cached_result.decision.verifier,
            )
            return OnlineRouterResult(decision, 0, 0, 0, ())

        result = verify_route(prompt, local, availability)
        if ttl > 0 and result.calls > 0:
            if len(self._route_cache) >= 100:
                oldest = next(iter(self._route_cache))
                self._route_cache.pop(oldest, None)
            self._route_cache[key] = (now + ttl, result)
        return result

    def execute(self, prompt: str) -> RunResult:
        started = time.monotonic()
        job_id = self.history.start(prompt)
        provider = "jarvis"
        kind = "general"
        decision = RoutingDecision("jarvis", "general", 0.0)
        router_result = OnlineRouterResult(decision, 0, 0, 0, ())
        worker_tokens = 0
        api_calls = 0

        try:
            self._emit("planner", "planejando", "regras locais primeiro · 0 tokens", "")
            self.refresh()
            availability = self.provider_status()
            local = local_route(prompt, availability)

            if self.demo:
                decision = local
            else:
                router_result = self._cached_verify(prompt, local, availability)
                decision = router_result.decision
                api_calls += router_result.calls

            provider = decision.provider
            kind = decision.kind
            route_detail = (
                f"{kind} · {decision.source} · confiança {decision.confidence:.0%}"
            )
            if decision.verifier:
                route_detail += f" · verificado por {decision.verifier}"
            self._emit("router", "roteando", route_detail, provider)
            log_activity(
                f"NEXUS: {decision.source} roteou '{prompt[:70]}' para {provider} "
                f"({decision.confidence:.0%})"
            )

            if self.demo:
                result = self._run_demo(
                    job_id, prompt, decision, started,
                )
                return result

            if provider == "jarvis":
                self._emit(
                    "jarvis",
                    "executando",
                    "memória + tools + permissões do JARVIS",
                    "jarvis",
                )
                text = self.jarvis.process(prompt, response_mode="text")
                self._output(text)
            else:
                memories = long_term_memory.recall_relevant(prompt, limit=5)
                plugin_context = (
                    describe_plugins(self.plugin_registry, decision.plugins)
                    if self.plugin_registry is not None else ""
                )
                delegated_prompt = worker_prompt(prompt, memories, plugin_context)
                spec = self._providers.get(provider)
                transport = spec.transport if spec else "?"
                self._emit(
                    "worker",
                    "executando",
                    f"{provider} via {transport} · apenas 1 worker",
                    provider,
                )

                run = run_provider(
                    provider,
                    delegated_prompt,
                    timeout=self.timeout,
                    max_output_chars=self.max_output,
                    max_api_tokens=self.max_api_tokens,
                    on_line=self._output,
                )
                worker_tokens += run.total_tokens
                if spec is not None and spec.transport == "api":
                    api_calls += 1

                # Workers externos não recebem credenciais. Quando precisam de
                # uma integração, pedem uma capability por marcador NEXUS_PLUGIN.
                # O broker executa no JARVIS com PermissionManager e devolve só o resultado.
                if run.ok and self.plugin_registry is not None and decision.plugins:
                    plugin_results = execute_requests(
                        self.plugin_registry,
                        run.text,
                        allowed=set(decision.plugins),
                    )
                    if plugin_results:
                        self._emit(
                            "plugins",
                            "executando",
                            f"{len(plugin_results)} chamada(s) protegida(s)",
                            provider,
                        )
                        followup = (
                            "Continue a tarefa usando os resultados abaixo. "
                            "Não repita chamadas já concluídas.\n\n"
                            + json.dumps(plugin_results, ensure_ascii=False)[:12000]
                        )
                        second = run_provider(
                            provider,
                            followup,
                            timeout=self.timeout,
                            max_output_chars=self.max_output,
                            max_api_tokens=self.max_api_tokens,
                            on_line=self._output,
                        )
                        worker_tokens += second.total_tokens
                        if spec is not None and spec.transport == "api":
                            api_calls += 1
                        if second.ok:
                            run = second

                if not run.ok:
                    self._emit(
                        "router",
                        "fallback",
                        f"{provider} falhou; JARVIS assume sem chamar outra IA",
                        "jarvis",
                    )
                    fallback_reason = run.text[-500:] if run.text else "sem saída"
                    self._output(f"[NEXUS] {provider} falhou: {fallback_reason}")
                    text = self.jarvis.process(prompt, response_mode="text")
                    self._output(text)
                    provider = f"{provider}→jarvis"
                else:
                    text = run.text

            self._emit(
                "reviewer",
                "revisando",
                "checagem local · nenhuma segunda IA por padrão",
                provider,
            )
            if not text.strip():
                text = "O worker terminou sem retornar conteúdo."

            elapsed = time.monotonic() - started
            result = RunResult(
                ok=True,
                provider=provider,
                kind=kind,
                text=text,
                elapsed=elapsed,
                route_source=decision.source,
                route_confidence=decision.confidence,
                router_calls=router_result.calls,
                router_tokens=router_result.prompt_tokens + router_result.completion_tokens,
                worker_tokens=worker_tokens,
                api_calls=api_calls,
            )
            self.history.finish(job_id, result)
            log_activity(
                f"NEXUS concluiu via {provider} em {elapsed:.1f}s; "
                f"APIs={api_calls}, tokens rastreados={result.router_tokens + worker_tokens}"
            )
            self._emit("reviewer", "concluído", "entrega pronta", provider)
            return result
        except Exception as exc:
            elapsed = time.monotonic() - started
            error = f"NEXUS não conseguiu concluir a tarefa: {exc}"
            self._output(error)
            result = RunResult(
                ok=False,
                provider=provider,
                kind=kind,
                text=error,
                elapsed=elapsed,
                route_source=decision.source,
                route_confidence=decision.confidence,
                router_calls=router_result.calls,
                router_tokens=router_result.prompt_tokens + router_result.completion_tokens,
                worker_tokens=worker_tokens,
                api_calls=api_calls,
            )
            self.history.finish(job_id, result)
            self._emit("nexus", "erro", str(exc), provider)
            return result

    def _run_demo(
        self,
        job_id: int,
        prompt: str,
        decision: RoutingDecision,
        started: float,
    ) -> RunResult:
        stages = (
            ("planner", "planejando", "regras locais · 0 tokens"),
            ("router", "roteando", f"selecionado: {decision.provider}"),
            ("worker", "executando", "simulação sem provider externo"),
            ("reviewer", "revisando", "validação local"),
        )
        for actor, state, message in stages:
            self._emit(actor, state, message, decision.provider)
            self._output(f"[DEMO] {actor}: {message}")
            time.sleep(0.12)
        text = (
            "Modo DEMO concluído: nenhum provider online/CLI foi chamado e nenhum token foi gasto."
        )
        self._output(text)
        elapsed = time.monotonic() - started
        result = RunResult(
            True,
            f"demo:{decision.provider}",
            decision.kind,
            text,
            elapsed,
            route_source=decision.source,
            route_confidence=decision.confidence,
        )
        self.history.finish(job_id, result)
        self._emit("reviewer", "concluído", "demo finalizada", decision.provider)
        return result

    def shutdown(self) -> None:
        self.jarvis.shutdown()
