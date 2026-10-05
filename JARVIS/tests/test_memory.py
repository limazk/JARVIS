"""Testes de memória: longo prazo, notas e log de atividade/conversas (seções 29/30)."""
from memory.conversations import log_message, recent_messages
from memory.database import log_activity, recent_activities
from memory.memory import recall_relevant, remember_fact
from tools.notes import add_note, list_notes, remove_note


def test_remember_and_recall():
    remember_fact(fact="meu editor é o VS Code")
    results = recall_relevant("qual é o meu editor")
    assert any("VS Code" in r for r in results)


def test_recall_sem_correspondencia_retorna_vazio():
    remember_fact(fact="minha cor favorita é azul")
    results = recall_relevant("previsão do tempo em Brasília")
    assert results == [] or all("azul" not in r for r in results)


def test_remember_fact_nao_duplica_o_mesmo_fato():
    from memory.database import get_connection

    remember_fact(fact="meu editor é o VS Code")
    remember_fact(fact="meu editor é o VS Code")

    with get_connection() as conn:
        rows = conn.execute("SELECT COUNT(*) AS n FROM memories WHERE value = ?", ("meu editor é o VS Code",)).fetchall()
    assert rows[0]["n"] == 1


def test_recall_relevant_prioriza_o_fato_mais_recente():
    remember_fact(fact="moro em Curitiba")
    remember_fact(fact="moro em São Paulo")

    results = recall_relevant("onde eu moro")

    assert results
    assert "São Paulo" in results[0]  # o mais recente vem primeiro (ORDER BY id DESC)


def test_notes_crud():
    add_note(text="comprar leite")
    listed = list_notes()
    assert "comprar leite" in listed.message

    removed = remove_note(text="leite")
    assert removed.success

    listed_again = list_notes()
    assert "comprar leite" not in listed_again.message


def test_activity_log():
    log_activity("Teste de atividade")
    rows = recent_activities(limit=5)
    assert any(row["description"] == "Teste de atividade" for row in rows)


def test_conversation_log():
    log_message("user", "olá")
    log_message("assistant", "oi, tudo bem?")
    rows = recent_messages(limit=5)
    contents = [row["content"] for row in rows]
    assert "olá" in contents
    assert "oi, tudo bem?" in contents
