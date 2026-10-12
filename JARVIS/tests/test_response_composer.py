from core.brain import LLMDecision
from personality.response import ResponseComposer


class _FakeLLM:
    def __init__(self, result):
        self.result = result
        self.calls = 0
        self.last_tools = None

    def decide(self, system_prompt, messages, tools):
        self.calls += 1
        self.last_tools = tools
        return self.result


def test_fast_path_never_calls_llm(monkeypatch):
    from config.settings import settings
    monkeypatch.setattr(settings, "user_title", "Senhor")
    llm = _FakeLLM(LLMDecision(kind="text", text="inventado"))
    output = ResponseComposer(llm).compose(
        tool_name="get_today_tasks", tool_result="Você tem 2 tarefas.",
        success=True, user_text="minhas tarefas", response_mode="voice", local_intent=True
    )
    assert llm.calls == 0
    assert output.startswith("Senhor,")


def test_complex_read_can_narrate_without_tools(monkeypatch):
    from config.settings import settings
    monkeypatch.setattr(settings, "natural_tool_responses", True)
    llm = _FakeLLM(LLMDecision(kind="text", text="Encontrei 2 resultados no link https://example.com"))
    result = ResponseComposer(llm).compose(
        tool_name="web_search", tool_result="2 resultados: https://example.com",
        success=True, user_text="pesquise", response_mode="text"
    )
    assert result.startswith("Encontrei")
    assert llm.last_tools == []


def test_changed_numbers_are_rejected(monkeypatch):
    from config.settings import settings
    monkeypatch.setattr(settings, "natural_tool_responses", True)
    llm = _FakeLLM(LLMDecision(kind="text", text="Há 900 tarefas."))
    original = "Há 2 tarefas."
    result = ResponseComposer(llm).compose(
        tool_name="list_notes", tool_result=original,
        success=True, user_text="minhas notas", response_mode="text"
    )
    assert result == original


def test_writes_are_not_narrated(monkeypatch):
    from config.settings import settings
    monkeypatch.setattr(settings, "natural_tool_responses", True)
    llm = _FakeLLM(LLMDecision(kind="text", text="Pronto"))
    result = ResponseComposer(llm).compose(
        tool_name="run_shell_command", tool_result="Comando executado.",
        success=True, user_text="rode comando", response_mode="voice"
    )
    assert result == "Comando executado."
    assert llm.calls == 0
