from __future__ import annotations

import pytest

from config.settings import settings
from integrations.rotina import RotinaAuthError, RotinaClient, RotinaProcessManager
from core.intent import match_local_intent


class FakeHTTPResponse:
    def __init__(self, data, status_code=200):
        self.data = data
        self.status_code = status_code
        self.ok = status_code < 400
        self.content = b"data"

    def json(self):
        return self.data


class FakeSession:
    def __init__(self, handler):
        self.handler = handler

    def request(self, method, url, **kwargs):
        return self.handler(method, url, kwargs)


def test_rotina_health(monkeypatch):
    client = RotinaClient()
    client._session = FakeSession(lambda *args: FakeHTTPResponse({"status": "ok"}))
    assert client.health()["status"] == "ok"


def test_rotina_authentication_error(monkeypatch):
    client = RotinaClient()
    client._session = FakeSession(lambda *args: FakeHTTPResponse({}, 401))
    with pytest.raises(RotinaAuthError):
        client.tasks()


def test_rotina_tasks_and_add_transaction(monkeypatch):
    calls = []

    def open_url(method, url, kwargs):
        calls.append((method, url, kwargs))
        if method == "GET":
            return FakeHTTPResponse([{"id": "1", "title": "Teste"}])
        return FakeHTTPResponse({"id": "tx1", "amount": 35})

    client = RotinaClient(api_key="fake")
    client._session = FakeSession(open_url)
    assert client.tasks()[0]["title"] == "Teste"
    assert client.add_transaction("out", 35, "comida")["id"] == "tx1"
    assert calls[-1][2]["headers"]["X-Api-Key"] == "fake"


def test_rotina_auto_start_mocked(monkeypatch, tmp_path):
    (tmp_path / "server.py").write_text("# fake")
    monkeypatch.setattr(settings, "rotina_enabled", True)
    monkeypatch.setattr(settings, "rotina_auto_start", True)
    monkeypatch.setattr(settings, "rotina_dir", str(tmp_path))

    class Client:
        calls = 0
        def health(self):
            self.calls += 1
            if self.calls == 1:
                from integrations.rotina import RotinaError
                raise RotinaError("off")
            return {"status": "ok"}

    class Process:
        returncode = None
        def poll(self): return None
        def terminate(self): pass
        def wait(self, timeout=None): return 0

    monkeypatch.setattr("integrations.rotina.subprocess.Popen", lambda *a, **k: Process())
    manager = RotinaProcessManager(client=Client())
    assert manager.ensure_running(wait_seconds=0.5)
    assert manager.started_by_jarvis


def test_rotina_failed_server_does_not_crash(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "rotina_enabled", True)
    monkeypatch.setattr(settings, "rotina_auto_start", True)
    monkeypatch.setattr(settings, "rotina_dir", str(tmp_path))

    class Offline:
        def health(self):
            from integrations.rotina import RotinaError
            raise RotinaError("off")

    assert not RotinaProcessManager(client=Offline()).ensure_running(wait_seconds=0)


@pytest.mark.parametrize(("phrase", "tool"), [
    ("Quais são minhas tarefas?", "get_today_tasks"),
    ("Adiciona testar o Jarvis nas tarefas de hoje.", "add_task"),
    ("Marca testar o Jarvis como concluído.", "complete_task"),
    ("Gastei 35 reais com comida.", "add_expense"),
    ("Ganhei 150 reais hoje.", "add_income"),
    ("Quanto entrou essa semana?", "get_financial_summary"),
    ("Quanto lucrei essa semana?", "get_business_summary"),
    ("Como estou comparado à semana passada?", "compare_weekly_finance"),
])
def test_rotina_natural_commands(phrase, tool):
    match = match_local_intent(phrase)
    assert match.matched and match.tool_name == tool
