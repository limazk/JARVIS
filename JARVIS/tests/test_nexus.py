"""Testes do roteamento NEXUS sem chamar APIs externas."""
from nexus.providers import worker_prompt
from nexus.router import choose_provider, classify


def test_classifica_codigo_sem_llm():
    assert classify("corrija esse bug no código Python") == "code"


def test_classifica_pesquisa_sem_llm():
    assert classify("pesquise documentação e fontes sobre isso") == "research"


def test_intent_local_do_jarvis_tem_prioridade():
    provider, kind = choose_provider(
        "que horas são",
        {"jarvis": True, "codex": True, "claude": True, "gemini": True, "ollama": True},
    )
    assert provider == "jarvis"
    assert kind == "jarvis_tool"


def test_codigo_prefere_codex_quando_disponivel():
    provider, kind = choose_provider(
        "implemente uma API Python",
        {"jarvis": True, "codex": True, "claude": True, "gemini": True, "ollama": True},
    )
    assert provider == "codex"
    assert kind == "code"


def test_codigo_cai_para_jarvis_se_workers_estao_offline():
    provider, kind = choose_provider(
        "implemente uma API Python",
        {"jarvis": True, "codex": False, "claude": False, "gemini": False, "ollama": False},
    )
    assert provider == "jarvis"
    assert kind == "code"


def test_worker_prompt_carrega_contexto_relevante():
    prompt = worker_prompt("revise o módulo", ["O usuário usa Linux."])
    assert "revise o módulo" in prompt
    assert "O usuário usa Linux." in prompt
    assert "JARVIS" in prompt
