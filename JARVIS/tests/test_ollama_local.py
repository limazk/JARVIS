from __future__ import annotations

import requests

from config.settings import settings
from core.brain import LocalProvider, OllamaHealth


class Response:
    def __init__(self, data, ok=True, status=200):
        self._data = data
        self.ok = ok
        self.status_code = status

    def json(self):
        return self._data

    def raise_for_status(self):
        if not self.ok:
            raise requests.HTTPError(str(self.status_code))


def test_ollama_offline(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError("off")))
    assert LocalProvider().health_check()[0] == OllamaHealth.OFFLINE


def test_ollama_online_model_missing(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: Response({"models": [{"name": "outro:latest"}]}))
    state, message = LocalProvider().health_check()
    assert state == OllamaHealth.MODEL_MISSING
    assert f"ollama pull {settings.local_llm_model}" in message


def test_ollama_server_online(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: Response({"models": []}))
    assert LocalProvider().server_status()[0] == OllamaHealth.ONLINE


def test_ollama_model_ready(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: Response({"models": [{"name": settings.local_llm_model}]}))
    assert LocalProvider().health_check()[0] == OllamaHealth.MODEL_READY


def test_ollama_online_http_error(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: Response({}, ok=False, status=500))
    assert LocalProvider().health_check()[0] == OllamaHealth.MODEL_ERROR


def test_ollama_tool_call_and_options(monkeypatch):
    captured = {}

    def post(url, json, timeout):
        captured.update(json)
        return Response({"message": {"tool_calls": [{"function": {"name": "get_time", "arguments": {}}}]}})

    monkeypatch.setattr(requests, "post", post)
    decision = LocalProvider().decide("system", [{"role": "user", "content": "hora"}], [{
        "name": "get_time", "description": "hora", "input_schema": {"type": "object", "properties": {}}
    }])
    assert decision.kind == "tool_call" and decision.tool_name == "get_time"
    assert captured["keep_alive"] == settings.ollama_keep_alive
    assert captured["options"]["num_ctx"] == settings.local_llm_context


def test_ollama_timeout_is_honest(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: (_ for _ in ()).throw(requests.Timeout("timeout")))
    decision = LocalProvider().decide("system", [], [])
    assert decision.kind == "text"
    assert "indisponível" in decision.text.lower()
    assert decision.retryable_error is True
