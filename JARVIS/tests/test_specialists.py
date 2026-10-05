"""Testes do roteamento para especialistas (core/specialists.py) — seção 49 do spec."""
from core.specialists import SPECIALISTS, pick_specialist


def test_pergunta_de_programacao_escolhe_developer():
    specialist = pick_specialist("meu script python está dando erro de importação")
    assert specialist is not None
    assert specialist.name == "JarvisDeveloper"


def test_pergunta_de_pesquisa_escolhe_researcher():
    specialist = pick_specialist("pesquisa quem foi Ada Lovelace")
    assert specialist is not None
    assert specialist.name == "JarvisResearcher"


def test_pergunta_de_sistema_escolhe_system():
    specialist = pick_specialist("quanto de bateria eu tenho")
    assert specialist is not None
    assert specialist.name == "JarvisSystem"


def test_frase_neutra_nao_escolhe_especialista():
    specialist = pick_specialist("bom dia")
    assert specialist is None


def test_todos_os_especialistas_tem_ferramentas_preferidas_reais():
    """
    `preferred_tools` só serve pra alguma coisa se os nomes existirem de
    verdade no registro de tools (tools/registry.py) — um nome errado
    aqui simplesmente nunca apareceria priorizado, silenciosamente.
    """
    from tools.registry import build_default_registry

    registry = build_default_registry()
    nomes_reais = {t.name for t in registry.all()}

    for specialist in SPECIALISTS:
        assert specialist.preferred_tools, f"{specialist.name} sem preferred_tools"
        for tool_name in specialist.preferred_tools:
            assert tool_name in nomes_reais, f"{specialist.name} referencia tool inexistente: {tool_name}"


def test_context_builder_do_sistema_traz_dado_real():
    specialist = next(s for s in SPECIALISTS if s.name == "JarvisSystem")
    assert specialist.context_builder is not None

    context = specialist.context_builder()

    # psutil está instalado neste sandbox, então sempre vem preenchido.
    assert "CPU" in context
    assert "%" in context


def test_context_builder_da_produtividade_reflete_lembretes_reais():
    # O banco já vem isolado por teste (ver tests/conftest.py::_isolated_database).
    specialist = next(s for s in SPECIALISTS if s.name == "JarvisProductivity")
    assert specialist.context_builder is not None

    sem_lembretes = specialist.context_builder()
    assert "não tem nenhum lembrete" in sem_lembretes

    from tools.reminders import add_reminder

    add_reminder("em 10 minutos de estudar")

    com_lembrete = specialist.context_builder()
    assert "1 lembrete pendente" in com_lembrete


def test_context_builder_nunca_levanta_excecao_com_banco_quebrado(monkeypatch):
    import memory.database as database_mod

    def _quebrado():
        raise RuntimeError("banco indisponível")

    monkeypatch.setattr(database_mod, "get_connection", _quebrado)

    specialist = next(s for s in SPECIALISTS if s.name == "JarvisProductivity")
    assert specialist.context_builder() == ""


def test_especialistas_sem_context_builder_nao_quebram():
    for specialist in SPECIALISTS:
        if specialist.name in ("JarvisDeveloper", "JarvisResearcher", "JarvisFiles"):
            assert specialist.context_builder is None
