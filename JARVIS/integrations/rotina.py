"""Cliente e lifecycle manager centralizados para a API local do ROTINA."""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
import urllib.parse
from datetime import date as Date
from pathlib import Path
from typing import Any

from config.settings import settings
from core.performance import measure

logger = logging.getLogger("jarvis.rotina")


class RotinaError(RuntimeError):
    pass


class RotinaAuthError(RotinaError):
    pass


class RotinaClient:
    def __init__(self, url: str | None = None, api_key: str | None = None, timeout: float = 5) -> None:
        self.url = (url or settings.rotina_url).rstrip("/")
        self.api_key = settings.rotina_key if api_key is None else api_key
        self.timeout = timeout
        self._session = None
        self._cache: dict[str, tuple[float, Any]] = {}
        self._cache_lock = threading.RLock()

    def _http(self):
        if self._session is None:
            import requests
            self._session = requests.Session()
        return self._session

    def _cached(self, key: str, loader) -> Any:
        if not settings.fast_cache_enabled:
            return loader()
        now = time.monotonic()
        with self._cache_lock:
            cached = self._cache.get(key)
            if cached and cached[0] > now:
                return cached[1]
        value = loader()
        ttl = max(0, settings.fast_cache_ttl)
        with self._cache_lock:
            self._cache[key] = (time.monotonic() + ttl, value)
        return value

    def invalidate(self, *keys: str) -> None:
        with self._cache_lock:
            if not keys:
                self._cache.clear()
                return
            for key in keys:
                self._cache.pop(key, None)

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.api_key:
            headers["X-Api-Key"] = self.api_key
        try:
            with measure("rotina_api_duration"):
                response = self._http().request(
                    method, f"{self.url}{path}", json=body, headers=headers, timeout=self.timeout
                )
            if response.status_code in (401, 403):
                raise RotinaAuthError("ROTINA recusou a autenticação; confira ROTINA_KEY.")
            if not response.ok:
                raise RotinaError(f"ROTINA respondeu HTTP {response.status_code}.")
            return response.json() if response.content else {}
        except RotinaError:
            raise
        except Exception as exc:
            raise RotinaError(f"ROTINA indisponível em {self.url}: {exc}") from exc

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/api/health")

    def summary(self) -> dict[str, Any]:
        return self._cached("routine_today", lambda: self._request("GET", "/api/summary"))

    def weekly_summary(self) -> dict[str, Any]:
        return self._cached("weekly_summary", lambda: self._request("GET", "/api/summary?period=week"))

    def tasks(self) -> list[dict[str, Any]]:
        return self._cached("tasks", lambda: self._request("GET", "/api/tasks"))

    def today_tasks(self) -> list[dict[str, Any]]:
        today = time.strftime("%Y-%m-%d")
        weekday = int(time.strftime("%w"))
        return self._cached("today_tasks", lambda: [task for task in self.tasks() if task.get("date") == today or task.get("recur") == "daily"
                or (task.get("recur") == "weekly" and int(task.get("weekday", -1)) == weekday)]
        )

    def add_task(self, title: str, date: str | None = None, time_text: str = "", category: str = "Pessoal",
                 priority: str = "media") -> dict[str, Any]:
        title = title.strip()
        if not title:
            raise ValueError("O título da tarefa não pode ficar vazio.")
        if len(title) > 200:
            raise ValueError("O título da tarefa deve ter no máximo 200 caracteres.")
        if date:
            try:
                Date.fromisoformat(date)
            except ValueError as exc:
                raise ValueError("A data deve usar o formato AAAA-MM-DD.") from exc
        if priority not in {"baixa", "media", "alta"}:
            raise ValueError("Prioridade deve ser baixa, media ou alta.")
        result = self._request("POST", "/api/tasks", {
            "title": title, "time": time_text.strip(), "cat": category.strip() or "Pessoal",
            "prio": priority, "date": date or time.strftime("%Y-%m-%d"), "recur": "none", "doneDates": [],
        })
        self.invalidate("tasks", "today_tasks", "routine_today", "weekly_summary")
        return result

    def complete_task(self, title_or_id: str, date: str | None = None) -> dict[str, Any]:
        query = title_or_id.strip().lower()
        if not query:
            raise ValueError("Informe a tarefa que deve ser concluída.")
        task = next((item for item in self.tasks()
                     if str(item.get("id", "")).lower() == query or query in str(item.get("title", "")).lower()), None)
        if task is None:
            raise RotinaError("Tarefa não encontrada.")
        done_date = date or time.strftime("%Y-%m-%d")
        done_dates = list(dict.fromkeys([*(task.get("doneDates") or []), done_date]))
        result = self._request("PATCH", f"/api/tasks/{urllib.parse.quote(str(task['id']))}", {"doneDates": done_dates})
        self.invalidate("tasks", "today_tasks", "routine_today", "weekly_summary")
        return result

    def transactions(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/transactions")

    def add_transaction(self, kind: str, amount: float, description: str, category: str = "Outros",
                        date: str | None = None) -> dict[str, Any]:
        if kind not in {"in", "out"}:
            raise ValueError("Tipo de transação deve ser 'in' ou 'out'.")
        amount = float(amount)
        if amount <= 0:
            raise ValueError("O valor deve ser maior que zero.")
        description = description.strip()
        if not description:
            raise ValueError("A descrição não pode ficar vazia.")
        if len(description) > 200:
            raise ValueError("A descrição deve ter no máximo 200 caracteres.")
        if date:
            try:
                Date.fromisoformat(date)
            except ValueError as exc:
                raise ValueError("A data deve usar o formato AAAA-MM-DD.") from exc
        result = self._request("POST", "/api/transactions", {
            "type": kind, "amount": amount, "desc": description,
            "cat": category.strip() or "Outros", "date": date or time.strftime("%Y-%m-%d"),
        })
        self.invalidate("weekly_summary", "routine_today")
        return result

    def businesses(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/businesses")

    def business_entries(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/bizEntries")

    def investments(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/investments")

    def ideas(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/ideas")


class RotinaProcessManager:
    """Só encerra o processo que esta instância efetivamente iniciou."""

    def __init__(self, client: RotinaClient | None = None) -> None:
        self.client = client or RotinaClient()
        self.process: subprocess.Popen | None = None

    @property
    def started_by_jarvis(self) -> bool:
        return self.process is not None

    def _server_dir(self) -> Path:
        if settings.rotina_dir.strip():
            return Path(settings.rotina_dir).expanduser().resolve()
        return settings.base_dir.parent / "ROTINA"

    def ensure_running(self, wait_seconds: float = 8.0) -> bool:
        if not settings.rotina_enabled:
            return False
        try:
            self.client.health()
            logger.info("ROTINA já está em execução; reutilizando processo existente.")
            return True
        except RotinaError:
            pass
        if not settings.rotina_auto_start:
            logger.warning("ROTINA indisponível e ROTINA_AUTO_START=false.")
            return False
        server_dir = self._server_dir()
        server = server_dir / "server.py"
        if not server.is_file():
            logger.warning("server.py do ROTINA não encontrado em %s.", server_dir)
            return False
        kwargs: dict[str, Any] = {
            "cwd": str(server_dir), "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
        }
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        else:
            kwargs["start_new_session"] = True
        try:
            self.process = subprocess.Popen([sys.executable, str(server), "--no-browser"], **kwargs)
        except OSError as exc:
            logger.warning("Não consegui iniciar o ROTINA: %s", exc)
            return False
        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                logger.warning("ROTINA encerrou durante a inicialização (código %s).", self.process.returncode)
                self.process = None
                return False
            try:
                self.client.health()
                logger.info("ROTINA iniciado em background pelo JARVIS.")
                return True
            except RotinaError:
                time.sleep(0.2)
        logger.warning("ROTINA não ficou pronto dentro de %.1fs; JARVIS continuará sem ele.", wait_seconds)
        return False

    def stop(self) -> None:
        if self.process is None or not settings.rotina_stop_on_exit:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        self.process = None
