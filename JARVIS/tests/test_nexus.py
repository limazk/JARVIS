"""Testes do NEXUS sem chamar APIs externas."""
from nexus.online_router import parse_router_json
from nexus.providers import worker_prompt
from nexus.router import choose_provider, classify, classify_with_confidence, local_route


def test_classifica_codigo_sem_llm():
    assert classify("corrija esse bug no código Python") == "code"


def test_classifica_pesquisa_sem_llm():
    assert classify("pesquise documentação e fontes sobre isso") == "research"


def test_intent_local_do_jarvis_tem_prioridade():
    decision = local_route(
        "que horas são",
        {"jarvis": True, "codex": True, "claude": True, "gemini": True},
    )
    assert decision.provider == "jarvis"
    assert decision.kind == "jarvis_tool"
    assert decision.confidence == 1.0


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


def test_mensagem_ambigua_tem_baixa_confianca_e_pode_ser_verificada_online():
    kind, confidence = classify_with_confidence("quero melhorar isso")
    assert kind == "general"
    assert confidence < 0.85


def test_duas_pistas_de_codigo_evitam_router_online_por_padrao():
    kind, confidence = classify_with_confidence("corrija o bug Python")
    assert kind == "code"
    assert confidence >= 0.85


def test_parse_router_json_puro():
    data = parse_router_json(
        '{"route":"groq","kind":"general","confidence":0.91,"needs_ai":true,"reason":"rápido"}'
    )
    assert data["route"] == "groq"
    assert data["confidence"] == 0.91


def test_parse_router_json_com_markdown():
    data = parse_router_json(
        '```json\n{"route":"openrouter","kind":"review","confidence":0.88,"needs_ai":true,"reason":"fallback"}\n```'
    )
    assert data["route"] == "openrouter"


def test_worker_prompt_carrega_contexto_relevante_sem_historico_inteiro():
    prompt = worker_prompt("revise o módulo", ["O usuário usa Linux."])
    assert "revise o módulo" in prompt
    assert "O usuário usa Linux." in prompt
    assert "Raiz do projeto" in prompt
