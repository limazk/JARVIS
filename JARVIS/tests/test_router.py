"""Testes do Router (core/router.py) — seção 32 do spec."""
from config.settings import settings
from core.agent import JarvisAgent
from core.brain import LLMDecision, LLMProvider
from core.context import ConversationContext
from core.permissions import PermissionManager
from core.router import Router, _build_system_prompt
from tools.registry import ToolRegistry


def test_comando_local_funciona_sem_llm():
    agent = JarvisAgent(confirm_callback=lambda message: True)
    try:
        reply = agent.process("que horas são")
        assert "são" in reply.lower()
    finally:
        agent.shutdown()


def test_calculo_local_nao_depende_de_ia():
    agent = JarvisAgent(confirm_callback=lambda message: True)
    try:
        reply = agent.process("calcula 20 vezes 3")
        assert "60" in reply
    finally:
        agent.shutdown()


class _FakeLLM(LLMProvider):
    available = True

    def __init__(self, tool_name: str = "tool_que_nao_existe") -> None:
        self.tool_name = tool_name

    def decide(self, system_prompt, messages, tools):
        return LLMDecision(kind="tool_call", tool_name=self.tool_name, tool_input={})


def test_tool_desconhecida_e_reportada_honestamente_nunca_finge_sucesso():
    registry = ToolRegistry()  # registro vazio de propósito
    permissions = PermissionManager(confirm_callback=lambda message: True)
    router = Router(_FakeLLM(), registry, ConversationContext(), permissions)

    result = router.handle("faça algo bem específico e incomum que não existe")

    assert result.success is False
    assert "não tenho a ferramenta" in result.reply.lower()


class _CapturingLLM(LLMProvider):
    """Fake LLM que só guarda o que recebeu (system_prompt e tools), pra inspecionar depois."""

    available = True

    def __init__(self) -> None:
        self.last_system_prompt = None
        self.last_tools = None

    def decide(self, system_prompt, messages, tools):
        self.last_system_prompt = system_prompt
        self.last_tools = tools
        return LLMDecision(kind="text", text="ok")


def test_system_prompt_inclui_user_title_quando_configurado(monkeypatch):
    monkeypatch.setattr(settings, "user_title", "Senhor")
    llm = _CapturingLLM()
    registry = ToolRegistry()
    permissions = PermissionManager(confirm_callback=lambda message: True)
    router = Router(llm, registry, ConversationContext(), permissions)

    router.handle("me conte uma curiosidade bem aleatória")

    assert llm.last_system_prompt is not None
    assert "Senhor" in llm.last_system_prompt


def test_system_prompt_sem_user_title_quando_desligado(monkeypatch):
    monkeypatch.setattr(settings, "user_title", "")
    prompt = _build_system_prompt()
    assert "dirija ao usuário chamando-o" not in prompt


def test_system_prompt_instrui_guardar_fatos_proativamente():
    prompt = _build_system_prompt()
    assert "remember_fact" in prompt


def test_system_prompt_inclui_data_e_hora_atuais():
    from datetime import datetime

    prompt = _build_system_prompt()
    ano_atual = str(datetime.now().year)
    assert "Data e hora atuais" in prompt
    assert ano_atual in prompt


def _router_com_registro_real(llm) -> Router:
    """
    Router com o ToolRegistry de verdade (tools/registry.py::build_default_registry)
    — precisa das tools reais registradas pra testar a reordenação por
    especialista (core/specialists.py::preferred_tools referencia nomes
    de tools de verdade).
    """
    from tools.registry import build_default_registry

    registry = build_default_registry()
    permissions = PermissionManager(confirm_callback=lambda message: True)
    return Router(llm, registry, ConversationContext(), permissions)


def test_especialista_reordena_tools_e_injeta_contexto_real():
    llm = _CapturingLLM()
    router = _router_com_registro_real(llm)

    router.handle("como está minha cpu e ram agora")

    assert llm.last_system_prompt is not None
    assert "Modo especialista: Sistema" in llm.last_system_prompt
    # O context_builder do especialista de Sistema coloca os números reais
    # (psutil) direto no prompt — sem precisar de uma tool call extra.
    assert "Estado real do sistema agora" in llm.last_system_prompt
    assert "CPU" in llm.last_system_prompt

    # As tools preferidas do especialista de Sistema vêm primeiro na lista.
    assert llm.last_tools is not None
    primeiro_nome = llm.last_tools[0]["name"]
    assert primeiro_nome in ("system_status", "disk_space", "set_volume", "mute_volume", "lock_computer")
    # Nenhuma ferramenta desaparece — só é reordenada.
    nomes = {t["name"] for t in llm.last_tools}
    assert "remember_fact" in nomes
    assert "web_search" in nomes


def test_mensagem_neutra_nao_reordena_nem_injeta_contexto_de_especialista():
    llm = _CapturingLLM()
    router = _router_com_registro_real(llm)

    router.handle("me conte uma curiosidade bem aleatória")

    assert "Modo especialista" not in llm.last_system_prompt
    assert router.last_specialist is None


def test_router_expoe_ultimo_especialista_selecionado():
    llm = _CapturingLLM()
    router = _router_com_registro_real(llm)

    assert router.last_specialist is None

    router.handle("minha internet wifi está travando")
    assert router.last_specialist == "JarvisSystem"

    router.handle("me explica quem foi Alan Turing")
    assert router.last_specialist == "JarvisResearcher"

    # "boa noite" (não "bom dia" — esse agora é um comando local, o
    # briefing matinal em tools/briefing.py, e nunca chega no especialista)
    router.handle("boa noite")
    assert router.last_specialist is None


def test_troca_de_especialista_e_registrada_na_atividade_mas_so_uma_vez_por_modo():
    from memory.database import recent_activities

    llm = _CapturingLLM()
    router = _router_com_registro_real(llm)

    router.handle("acho que minha cpu está sobrecarregada")
    router.handle("e a memória, como está")  # ainda Sistema — não deve logar de novo
    router.handle("me explica quem foi Alan Turing")  # trocou de modo — loga

    descricoes = [row["description"] for row in recent_activities(limit=20)]
    assert descricoes.count("Modo especialista: JarvisSystem") == 1
    assert descricoes.count("Modo especialista: JarvisResearcher") == 1
