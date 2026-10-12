from voice.formatting import prepare_speech


def test_clean_markdown_and_links_for_speech():
    message = "# Status\n**Você tem 3 tarefas.** [Abrir](https://example.com)"
    spoken = prepare_speech(message)
    assert "Status" in spoken
    assert "3 tarefas" in spoken
    assert "**" not in spoken
    assert "https://" not in spoken


def test_large_speech_has_safe_truncation():
    spoken = prepare_speech("texto " * 1000, max_chars=160)
    assert "restante está disponível na tela" in spoken
