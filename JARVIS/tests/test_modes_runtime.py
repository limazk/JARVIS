from core.brain import LLMDecision
from core.context import ConversationContext
from core.permissions import PermissionManager
from core.router import Router
from tools.registry import ToolRegistry


class _FakeLLM:
    def __init__(self):
        self.calls = 0
        self.prompt = ""

    def decide(self, system_prompt, messages, tools):
        self.calls += 1
        self.prompt = system_prompt
        return LLMDecision(kind="text", text="Entendido.")


def _router(llm):
    return Router(llm, ToolRegistry(), ConversationContext(), PermissionManager())


def test_mode_switch_is_local_and_changes_next_prompt():
    llm = _FakeLLM()
    router = _router(llm)
    response = router.handle("Jarvis, ativa modo estudo")
    assert "study" in response.reply.lower()
    assert llm.calls == 0
    router.handle("me conte uma curiosidade bem aleatória")
    assert "Modo comportamental atual: STUDY" in llm.prompt
    assert "Ensine com exemplos" in llm.prompt


def test_mode_survives_router_restart():
    previous = _router(_FakeLLM())
    previous.handle("modo foco")
    fresh = _router(_FakeLLM())
    assert fresh.current_mode == "FOCUS"
    fresh.handle("modo normal")
    assert fresh.current_mode == "NORMAL"
