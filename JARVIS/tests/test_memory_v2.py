from memory.memory import remember_fact, recall_relevant, forget_fact


def test_new_city_supersedes_old_city():
    remember_fact(fact="moro em Curitiba")
    remember_fact(fact="moro em Recife")
    assert recall_relevant("qual é minha cidade") == ["moro em Recife"]


def test_memory_recognizes_simple_synonyms():
    remember_fact(fact="meu editor é o VS Code")
    assert "VS Code" in " ".join(recall_relevant("qual a minha IDE"))


def test_sensitive_secret_is_not_saved():
    result = remember_fact(fact="minha senha é topsecret123")
    assert not result.success
    assert recall_relevant("topsecret123") == []


def test_user_can_explicitly_forget():
    remember_fact(fact="minha cor favorita é azul")
    assert forget_fact(fact="cor favorita").success
    assert not recall_relevant("minha cor favorita")
