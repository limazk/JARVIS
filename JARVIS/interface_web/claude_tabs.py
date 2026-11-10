"""Abas independentes do Claude Code na interface pywebview do JARVIS.

Cada aba mantém um session_id próprio do Claude Code e um histórico local.
A execução utiliza autenticação Claude Max via CLI, NÃO a chave de API do
JARVIS. A interface de chat desabilita as tools do Claude (inclusive MCP).
Não modifica o NEXUS nem o shell tool existente.

Nenhum processo é iniciado ao abrir a janela; somente após o usuário enviar
uma mensagem. Nenhuma credencial é armazenada no banco de dados.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import subprocess
import threading
import uuid
from contextlib import closing
from pathlib import Path

from config.settings import settings

logger = logging.getLogger("jarvis.claude_tabs")
MAX_TABS = 12
MAX_PROMPT_CHARS = 12000
MAX_REPLY_CHARS = 30000
TIMEOUT_SECONDS = 240
MODELS = {"default", "sonnet", "opus"}


class ClaudeTabs:
    def __init__(self, db_path: Path | None = None, *, executable: str | None = None,
                 popen_factory=None) -> None:
        self.db_path = Path(db_path or settings.db_path.parent / "claude_tabs.sqlite3")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.executable = executable
        self._spawn = popen_factory or subprocess.Popen
        self._lock = threading.RLock()
        self._busy: set[str] = set()
        self._processes: dict[str, subprocess.Popen] = {}
        self._closed = False
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS claude_tabs (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    model TEXT NOT NULL DEFAULT 'default',
                    session_id TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS claude_tab_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tab_id TEXT NOT NULL REFERENCES claude_tabs(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'error')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS claude_tab_msg_lookup
                    ON claude_tab_messages(tab_id, id);
            """)
            conn.commit()

    def _tabs(self, conn: sqlite3.Connection) -> list[dict]:
        rows = conn.execute(
            "SELECT id, title, model, session_id, created_at, updated_at "
            "FROM claude_tabs ORDER BY updated_at DESC, created_at DESC"
        ).fetchall()
        return [
            {**dict(row), "busy": row["id"] in self._busy,
             "has_session": bool(row["session_id"])}
            for row in rows
        ]

    def snapshot(self, selected_id: str | None = None) -> dict:
        with self._lock, closing(self._connect()) as conn:
            tabs = self._tabs(conn)
            ids = {t["id"] for t in tabs}
            current = selected_id if selected_id in ids else (tabs[0]["id"] if tabs else None)
            messages: list[dict] = []
            if current:
                rows = conn.execute(
                    "SELECT id, role, content, created_at FROM "
                    "(SELECT id, role, content, created_at FROM claude_tab_messages "
                    "WHERE tab_id=? ORDER BY id DESC LIMIT 150) ORDER BY id",
                    (current,),
                ).fetchall()
                messages = [dict(row) for row in rows]
            return {
                "ok": True,
                "installed": bool(self.executable or shutil.which("claude")),
                "selected_id": current,
                "tabs": tabs,
                "messages": messages,
                "max_tabs": MAX_TABS,
                "subscription_mode": True,
            }

    def create(self, title: str = "", model: str = "default") -> dict:
        if model not in MODELS:
            return {"ok": False, "error": "Modelo inválido."}
        title = (title or "Nova conversa").strip()[:60] or "Nova conversa"
        with self._lock, closing(self._connect()) as conn:
            if self._closed:
                return {"ok": False, "error": "Janela sendo encerrada."}
            count = conn.execute("SELECT COUNT(*) FROM claude_tabs").fetchone()[0]
            if count >= MAX_TABS:
                return {"ok": False, "error": f"Limite de {MAX_TABS} abas atingido."}
            tab_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO claude_tabs(id, title, model) VALUES(?, ?, ?)",
                (tab_id, title, model),
            )
            conn.commit()
        return {"ok": True, "id": tab_id}

    def rename(self, tab_id: str, title: str) -> dict:
        title = (title or "").strip()[:60]
        if not title:
            return {"ok": False, "error": "O título não pode ficar vazio."}
        with self._lock, closing(self._connect()) as conn:
            cursor = conn.execute(
                "UPDATE claude_tabs SET title=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (title, tab_id),
            )
            conn.commit()
            return {"ok": bool(cursor.rowcount), "error": "Aba não encontrada." if not cursor.rowcount else ""}

    def delete(self, tab_id: str) -> dict:
        with self._lock, closing(self._connect()) as conn:
            if tab_id in self._busy:
                return {"ok": False, "error": "Aguarde a resposta antes de excluir esta aba."}
            cursor = conn.execute("DELETE FROM claude_tabs WHERE id=?", (tab_id,))
            conn.commit()
            return {"ok": bool(cursor.rowcount), "error": "Aba não encontrada." if not cursor.rowcount else ""}

    def send(self, tab_id: str, text: str) -> dict:
        text = (text or "").strip()
        if not text or len(text) > MAX_PROMPT_CHARS:
            return {"ok": False, "error": f"Envie entre 1 e {MAX_PROMPT_CHARS} caracteres."}
        binary = self.executable or shutil.which("claude")
        if not binary:
            return {"ok": False, "error": "Claude Code CLI não instalado. Instale e autentique com claude auth login."}
        with self._lock, closing(self._connect()) as conn:
            if self._closed:
                return {"ok": False, "error": "JARVIS está encerrando."}
            row = conn.execute(
                "SELECT id, session_id, model FROM claude_tabs WHERE id=?", (tab_id,)
            ).fetchone()
            if row is None:
                return {"ok": False, "error": "Aba não encontrada."}
            if tab_id in self._busy:
                return {"ok": False, "error": "Esta aba já está processando uma mensagem."}
            # Uma aba pode estar ocupada sem bloquear as outras.
            self._busy.add(tab_id)
            conn.execute(
                "INSERT INTO claude_tab_messages(tab_id, role, content) VALUES(?, 'user', ?)",
                (tab_id, text),
            )
            conn.execute(
                "UPDATE claude_tabs SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (tab_id,)
            )
            conn.commit()
            try:
                thread = threading.Thread(
                    target=self._worker, args=(tab_id, text, row["session_id"], row["model"], binary),
                    daemon=True, name=f"jarvis-claude-{tab_id[:8]}",
                )
                thread.start()
            except Exception:
                self._busy.discard(tab_id)
                raise
        return {"ok": True}

    def _invoke(self, tab_id: str, text: str, session_id: str | None,
                model: str, binary: str) -> tuple[str, str]:
        # Não herdar a chave .env da API do Jarvis: com Claude Max o login da
        # assinatura deve ser usado, sem cobranças não intencionais na Console.
        env = os.environ.copy()
        for key in (
            "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
            "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX",
            "CLAUDE_CODE_USE_FOUNDRY",
        ):
            env.pop(key, None)
        argv = [
            binary, "-p", text, "--output-format", "json",
            "--bare", "--tools", "", "--disallowedTools", "mcp__*",
            "--max-turns", "1",
        ]
        if model != "default":
            argv.extend(["--model", model])
        if session_id:
            argv.extend(["--resume", session_id])
        proc = self._spawn(
            argv,
            cwd=str(settings.base_dir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        with self._lock:
            if self._closed:
                proc.terminate()
                raise RuntimeError("JARVIS está encerrando.")
            self._processes[tab_id] = proc
        try:
            try:
                stdout, stderr = proc.communicate(timeout=TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired as exc:
                proc.kill()
                proc.communicate()
                raise RuntimeError("Claude demorou demais para responder (tempo limite de 240s).") from exc
        finally:
            with self._lock:
                self._processes.pop(tab_id, None)

        if proc.returncode != 0:
            detail = (stderr or stdout or "").lower()
            if any(term in detail for term in ("login", "auth", "not logged", "unauthorized")):
                raise RuntimeError("Claude não autenticado. Execute 'claude auth login' no terminal e escolha sua conta Max.")
            if "usage limit" in detail or "rate limit" in detail:
                raise RuntimeError("Limite de uso do Claude atingido. Verifique sua assinatura no CLI.")
            raise RuntimeError("Claude CLI falhou. Abra 'claude' no terminal para consultar o erro; a aba não cobrou a API do JARVIS.")
        try:
            payload = json.loads(stdout)
        except (ValueError, TypeError) as exc:
            raise RuntimeError("Claude CLI não retornou JSON válido. Atualize a instalação do Claude Code.") from exc
        if not isinstance(payload, dict) or payload.get("is_error"):
            raise RuntimeError("Claude retornou uma falha. Verifique o login e os limites de uso.")
        answer = payload.get("result")
        sid = payload.get("session_id")
        if not isinstance(answer, str) or not answer.strip():
            raise RuntimeError("Claude não retornou texto de resposta.")
        if not isinstance(sid, str):
            raise RuntimeError("Claude não retornou um ID de sessão válido.")
        try:
            uuid.UUID(sid)
        except ValueError as exc:
            raise RuntimeError("Claude retornou um ID de sessão inesperado.") from exc
        return answer[:MAX_REPLY_CHARS], sid

    def _worker(self, tab_id: str, text: str, session_id: str | None,
                model: str, binary: str) -> None:
        role = "assistant"
        new_sid: str | None = None
        try:
            content, new_sid = self._invoke(tab_id, text, session_id, model, binary)
        except Exception as exc:  # nunca expor segredos nem derrubar a interface
            logger.warning("Claude tab %s falhou (%s)", tab_id[:8], type(exc).__name__)
            role = "error"
            content = str(exc) if isinstance(exc, RuntimeError) else "Falha inesperada ao consultar Claude."
        finally:
            with self._lock:
                try:
                    with closing(self._connect()) as conn:
                        conn.execute(
                            "INSERT INTO claude_tab_messages(tab_id, role, content) VALUES(?, ?, ?)",
                            (tab_id, role, content),
                        )
                        if new_sid:
                            conn.execute(
                                "UPDATE claude_tabs SET session_id=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                                (new_sid, tab_id),
                            )
                        conn.commit()
                except sqlite3.Error:
                    logger.exception("Não foi possível persistir a resposta Claude.")
                self._busy.discard(tab_id)

    def shutdown(self) -> None:
        with self._lock:
            self._closed = True
            processes = list(self._processes.values())
        for proc in processes:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    proc.kill()
                except OSError:
                    pass
