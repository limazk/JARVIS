"""Claude Max tabs tests: mocked CLI only, no network or subscription usage."""
import json
import threading
import time
import uuid

import pytest

from interface_web.claude_tabs import ClaudeTabs, MAX_TABS


class FakeProcess:
    def __init__(self, argv, **kwargs):
        self.argv, self.kwargs = argv, kwargs
        self.returncode = 0

    def communicate(self, timeout=None):
        return json.dumps({
            "type": "result", "result": "Resposta",
            "session_id": str(uuid.uuid4()), "is_error": False,
        }), ""

    def terminate(self):
        self.returncode = -15

    def kill(self):
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


def idle(service, tab):
    until = time.monotonic() + 4
    while time.monotonic() < until:
        snap = service.snapshot(tab)
        if not next(t for t in snap["tabs"] if t["id"] == tab)["busy"]:
            return snap
        time.sleep(.01)
    pytest.fail("Simulated worker did not complete")


def test_independent_sessions_and_persistence(tmp_path):
    path = tmp_path / "claude_tabs.sqlite3"
    service = ClaudeTabs(path, executable="/fake/claude", popen_factory=FakeProcess)
    a = service.create("Código", "sonnet")["id"]
    b = service.create("Estudos", "opus")["id"]
    assert service.send(a, "Revise este código")["ok"]
    snapshot = idle(service, a)
    assert [msg["role"] for msg in snapshot["messages"]] == ["user", "assistant"]
    assert service.snapshot(b)["messages"] == []
    assert next(t for t in snapshot["tabs"] if t["id"] == a)["session_id"]
    second = ClaudeTabs(path, executable="/fake/claude", popen_factory=FakeProcess)
    assert len(second.snapshot(a)["messages"]) == 2
    assert second.snapshot(b)["messages"] == []
    second.shutdown()
    service.shutdown()


def test_resume_and_strip_billing_keys(tmp_path, monkeypatch):
    sid = str(uuid.uuid4())
    calls = []

    class Recorder(FakeProcess):
        def __init__(self, argv, **kwargs):
            super().__init__(argv, **kwargs)
            calls.append((argv, kwargs))

        def communicate(self, timeout=None):
            return json.dumps({"result": "ok", "session_id": sid}), ""

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-never-send")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://invalid.example")
    service = ClaudeTabs(tmp_path / "test.sqlite3", executable="/fake/claude", popen_factory=Recorder)
    tab = service.create("Implementação", "sonnet")["id"]
    assert service.send(tab, "primeiro")["ok"]
    idle(service, tab)
    assert service.send(tab, "segundo")["ok"]
    assert len(idle(service, tab)["messages"]) == 4
    assert "--resume" not in calls[0][0]
    assert calls[1][0][calls[1][0].index("--resume") + 1] == sid
    for argv, kwargs in calls:
        assert argv[argv.index("--tools") + 1] == ""
        assert argv[argv.index("--disallowedTools") + 1] == "mcp__*"
        assert "--bare" in argv
        assert kwargs["env"].get("ANTHROPIC_API_KEY") is None
        assert kwargs["env"].get("ANTHROPIC_BASE_URL") is None
    service.shutdown()


def test_validation_limits_rename_delete(tmp_path):
    service = ClaudeTabs(tmp_path / "test.sqlite3", executable="/fake/claude", popen_factory=FakeProcess)
    assert not service.create("x", "not-a-model")["ok"]
    ids = [service.create()["id"] for _ in range(MAX_TABS)]
    assert not service.create()["ok"]
    assert not service.send(ids[0], "")["ok"]
    assert not service.send(ids[0], "x" * 12001)["ok"]
    assert service.rename(ids[0], "Refatoração")["ok"]
    assert service.delete(ids[0])["ok"]
    assert service.create()["ok"]
    service.shutdown()


def test_missing_cli_does_not_store_message(tmp_path, monkeypatch):
    monkeypatch.setattr("interface_web.claude_tabs.shutil.which", lambda _: None)
    service = ClaudeTabs(tmp_path / "test.sqlite3")
    tab = service.create()["id"]
    assert not service.send(tab, "olá")["ok"]
    assert service.snapshot(tab)["messages"] == []
    service.shutdown()


def test_auth_failure_is_safe(tmp_path):
    class Unauthorized(FakeProcess):
        def __init__(self, argv, **kwargs):
            super().__init__(argv, **kwargs)
            self.returncode = 1

        def communicate(self, timeout=None):
            return "", "not logged in"

    service = ClaudeTabs(tmp_path / "test.sqlite3", executable="/fake/claude", popen_factory=Unauthorized)
    tab = service.create()["id"]
    assert service.send(tab, "oi")["ok"]
    messages = idle(service, tab)["messages"]
    assert messages[-1]["role"] == "error"
    assert "claude auth login" in messages[-1]["content"]
    service.shutdown()


def test_two_tabs_allow_parallel_work(tmp_path):
    began = threading.Event()
    release = threading.Event()

    class Slow(FakeProcess):
        def communicate(self, timeout=None):
            began.set()
            release.wait(timeout=2)
            return super().communicate(timeout)

    service = ClaudeTabs(tmp_path / "test.sqlite3", executable="/fake/claude", popen_factory=Slow)
    a, b = service.create()["id"], service.create()["id"]
    assert service.send(a, "A")["ok"]
    assert began.wait(timeout=1)
    assert not service.send(a, "duplicado")["ok"]
    assert service.send(b, "B")["ok"]
    release.set()
    idle(service, a)
    idle(service, b)
    service.shutdown()
