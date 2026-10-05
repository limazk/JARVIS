"""Instrumentação leve de latência por requisição, sem conteúdo do usuário."""
from __future__ import annotations

import contextvars
import logging
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

logger = logging.getLogger("jarvis.performance")
_current_trace: contextvars.ContextVar["PerformanceTrace | None"] = contextvars.ContextVar(
    "jarvis_performance_trace", default=None
)


@dataclass
class PerformanceTrace:
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    started_at: float = field(default_factory=time.perf_counter)
    metrics: dict[str, float] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _logged: bool = False

    def set(self, name: str, seconds: float) -> None:
        with self._lock:
            self.metrics[name] = max(0.0, float(seconds))

    def elapsed(self) -> float:
        return time.perf_counter() - self.started_at

    def mark_elapsed(self, name: str) -> None:
        self.set(name, self.elapsed())

    @contextmanager
    def measure(self, name: str) -> Iterator[None]:
        started = time.perf_counter()
        try:
            yield
        finally:
            self.set(name, time.perf_counter() - started)

    def log(self) -> None:
        with self._lock:
            if self._logged:
                return
            self.metrics.setdefault("total_request_duration", self.elapsed())
            values = dict(self.metrics)
            self._logged = True
        order = (
            "wake_to_stt", "stt_duration", "routing_duration", "tool_duration",
            "rotina_api_duration", "llm_first_token", "llm_total_duration",
            "tts_start_duration", "total_request_duration",
        )
        fields = " ".join(f"{name}={values.get(name, 0.0):.3f}s" for name in order)
        logger.info("PERF request=%s %s", self.request_id, fields)


def current_trace() -> PerformanceTrace | None:
    return _current_trace.get()


@contextmanager
def request_trace(trace: PerformanceTrace | None = None) -> Iterator[PerformanceTrace]:
    active = trace or PerformanceTrace()
    token = _current_trace.set(active)
    try:
        yield active
    finally:
        _current_trace.reset(token)


@contextmanager
def measure(name: str) -> Iterator[None]:
    trace = current_trace()
    if trace is None:
        yield
        return
    with trace.measure(name):
        yield
