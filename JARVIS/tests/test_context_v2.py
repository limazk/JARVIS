from core.context import ConversationContext
from memory.conversations import load_summary, save_summary


def test_bounded_recaps_exclude_current_short_term_window():
    ctx = ConversationContext(max_messages=2, summary_items=3)
    ctx.add("user", "A fase beta está pronta")
    ctx.add("assistant", "Precisa validar os testes")
    ctx.add("user", "Qual é o próximo passo?")
    ctx.add("assistant", "Abrir um PR")
    assert "A fase beta está pronta" in ctx.summary_text()
    assert "Precisa validar os testes" in ctx.summary_text()
    assert len(ctx.as_llm_messages()) == 2


def test_summary_survives_restore():
    ctx = ConversationContext(max_messages=2)
    ctx.add("user", "primeiro")
    ctx.add("assistant", "segundo")
    ctx.add("user", "terceiro")
    save_summary(ctx.summary_text())
    new_ctx = ConversationContext()
    new_ctx.restore_summary(load_summary())
    assert "primeiro" in new_ctx.summary_text()
    new_ctx.clear()
    assert not new_ctx.summary_text()
