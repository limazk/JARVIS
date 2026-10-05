"""
Testes de interface_web/bridge.py — a lógica de negócio da nova
interface (pywebview), sem nenhuma dependência do pacote `webview`
em si (que não está disponível neste ambiente — ver requirements.txt).

Como `WebBridge.__init__` cria um `JarvisAgent` de verdade (mesmo
padrão usado em tests/test_router.py: funciona sem chave de IA
configurada, resolvendo comandos locais como "que horas são"), cada
teste cria sua própria instância e chama `.shutdown()` no fim (via
fixture) pra não deixar o `ReminderScheduler` rodando em segundo
plano entre testes.
"""
from __future__ import annotations

import dataclasses
import time

import pytest

import config.settings as settings_module
from interface_web.bridge import WebBridge


@pytest.fixture(autouse=True)
def _restore_settings_singleton():
    """
    Vários métodos do WebBridge mudam o objeto `settings` compartilhado
    de verdade (wake_word_enabled, llm_provider, ...) — sem restaurar
    isso, um teste vazaria estado pros que rodarem depois dele (mesmo
    padrão de tests/test_settings_env_writer.py).
    """
    original = {f.name: getattr(settings_module.settings, f.name) for f in dataclasses.fields(settings_module.settings)}
    yield
    for name, value in original.items():
        setattr(settings_module.settings, name, value)


@pytest.fixture
def bridge():
    b = WebBridge()
    try:
        yield b
    finally:
        b.shutdown()


def _wait_until(predicate, timeout=5.0, interval=0.02):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def test_inicializa_com_mensagem_de_boas_vindas(bridge):
    messages = bridge.get_messages(0)

    assert len(messages) == 1
    assert messages[0]["speaker"] == "Jarvis"
    assert "online" in messages[0]["text"].lower()


def test_get_snapshot_traz_as_chaves_esperadas(bridge):
    snap = bridge.get_snapshot()

    for key in (
        "state", "stats", "module_rows", "process_rows", "activity_rows", "chat_unread",
        "pending_confirmation", "voice_enabled", "autostart_supported",
        "autostart_enabled", "tray_active", "wake_word", "jarvis_name", "llm_available",
        "uptime_seconds", "message_count", "active_specialist",
    ):
        assert key in snap
    assert len(snap["module_rows"]) == 9
    assert len(snap["process_rows"]) > 0  # sempre há pelo menos o processo do próprio teste
    assert snap["uptime_seconds"] >= 0
    assert snap["message_count"] == 1  # só a mensagem de "online" inicial até aqui
    assert snap["pending_confirmation"] is None
    assert snap["tray_active"] is False  # start_tray() nunca foi chamado neste teste
    assert snap["active_specialist"] is None  # nenhuma mensagem passou pelo LLM ainda


def test_send_text_processa_comando_local_em_segundo_plano(bridge):
    result = bridge.send_text("que horas são")
    assert result == {"ok": True}

    _wait_until(lambda: len(bridge.get_messages(0)) >= 3)

    messages = bridge.get_messages(0)
    assert messages[0]["speaker"] == "Jarvis"  # "online" inicial
    assert messages[1]["speaker"] == "Você"
    assert messages[1]["text"] == "que horas são"
    assert messages[2]["speaker"] == "Jarvis"
    assert "são" in messages[2]["text"].lower()


def test_send_text_com_texto_vazio_nao_faz_nada(bridge):
    result = bridge.send_text("   ")

    assert result == {"ok": False}
    assert len(bridge.get_messages(0)) == 1  # só a mensagem de "online" inicial


def test_get_messages_filtra_por_since_id(bridge):
    first_id = bridge.get_messages(0)[0]["id"]

    bridge.send_text("que horas são")
    _wait_until(lambda: len(bridge.get_messages(0)) >= 3)

    only_new = bridge.get_messages(first_id)
    assert all(m["id"] > first_id for m in only_new)
    assert len(only_new) == 2  # "Você" + resposta do Jarvis


def test_set_page_limpa_aviso_de_mensagem_nao_lida(bridge):
    bridge.send_text("que horas são")
    _wait_until(lambda: bridge.get_snapshot()["chat_unread"] is True)

    assert bridge.get_snapshot()["chat_unread"] is True

    bridge.set_page("chat")

    assert bridge.get_snapshot()["chat_unread"] is False


def test_confirmacao_bloqueia_ate_resposta_e_devolve_o_valor(bridge):
    import threading

    result_holder = {}

    def worker():
        result_holder["value"] = bridge._confirm_dialog("Confirma apagar os arquivos?")

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    _wait_until(lambda: bridge.get_snapshot()["pending_confirmation"] is not None)
    pending = bridge.get_snapshot()["pending_confirmation"]
    assert pending["message"] == "Confirma apagar os arquivos?"

    answer = bridge.answer_confirmation(pending["id"], True)
    assert answer == {"ok": True}

    t.join(timeout=5)
    assert result_holder["value"] is True
    assert bridge.get_snapshot()["pending_confirmation"] is None


def test_confirmacao_recusada_devolve_false(bridge):
    import threading

    result_holder = {}

    def worker():
        result_holder["value"] = bridge._confirm_dialog("Confirma?")

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    _wait_until(lambda: bridge.get_snapshot()["pending_confirmation"] is not None)
    pending = bridge.get_snapshot()["pending_confirmation"]

    bridge.answer_confirmation(pending["id"], False)
    t.join(timeout=5)

    assert result_holder["value"] is False


def test_answer_confirmation_com_id_desconhecido_nao_quebra(bridge):
    result = bridge.answer_confirmation(9999, True)

    assert result == {"ok": False}


def test_toggle_voice_sem_microfone_disponivel_desliga_sozinho(bridge, monkeypatch):
    from voice.listener import listener

    monkeypatch.setattr(listener, "is_ready", lambda: False)

    result = bridge.toggle_voice(True)

    assert result["ok"] is False
    assert result["enabled"] is False
    messages = bridge.get_messages(0)
    assert any("indisponível" in m["text"] for m in messages)


def test_request_mic_sem_fala_detectada_avisa_em_vez_de_ficar_mudo(bridge, monkeypatch):
    """
    Bug real reportado pelo usuário: ele falava e "parecia que o microfone
    não reconhecia" — o motivo era que qualquer falha em listen_once()
    (nenhuma fala detectada, fala não entendida, erro de captura) ficava
    muda, sem nenhuma mensagem. Agora cada motivo tem um aviso.
    """
    from voice.listener import ListenOutcome, listener

    monkeypatch.setattr(listener, "is_ready", lambda: True)
    monkeypatch.setattr(listener, "listen_once_detailed", lambda phrase_time_limit=None: ListenOutcome(text=None, reason="no_speech"))

    bridge.request_mic()
    _wait_until(lambda: len(bridge.get_messages(0)) >= 2)

    messages = bridge.get_messages(0)
    assert "Não ouvi nada" in messages[-1]["text"]


def test_request_mic_fala_nao_entendida_avisa_especificamente(bridge, monkeypatch):
    from voice.listener import ListenOutcome, listener

    monkeypatch.setattr(listener, "is_ready", lambda: True)
    monkeypatch.setattr(listener, "listen_once_detailed", lambda phrase_time_limit=None: ListenOutcome(text=None, reason="not_understood"))

    bridge.request_mic()
    _wait_until(lambda: len(bridge.get_messages(0)) >= 2)

    assert "não consegui entender" in bridge.get_messages(0)[-1]["text"].lower()


def test_request_mic_com_texto_processa_o_comando_normalmente(bridge, monkeypatch):
    from voice.listener import ListenOutcome, listener

    monkeypatch.setattr(listener, "is_ready", lambda: True)
    monkeypatch.setattr(listener, "listen_once_detailed", lambda phrase_time_limit=None: ListenOutcome(text="que horas são", reason="ok"))

    bridge.request_mic()
    _wait_until(lambda: len(bridge.get_messages(0)) >= 3)

    messages = bridge.get_messages(0)
    assert any(m["text"] == "que horas são" for m in messages)


def test_toggle_voice_desligar_nunca_falha(bridge):
    result = bridge.toggle_voice(False)

    assert result == {"ok": True, "enabled": False}


def test_toggle_autostart_fora_do_windows_retorna_erro(bridge):
    result = bridge.toggle_autostart(True)

    assert result["ok"] is False
    assert "error" in result


def test_get_llm_config_lista_provedores_e_provedor_atual(bridge):
    config = bridge.get_llm_config()

    values = [p["value"] for p in config["providers"]]
    assert "gemini" in values
    assert "local" in values
    ollama_entry = next(p for p in config["providers"] if p["value"] == "local")
    assert ollama_entry["needs_key"] is False
    gemini_entry = next(p for p in config["providers"] if p["value"] == "gemini")
    assert gemini_entry["needs_key"] is True


def test_save_llm_config_sem_chave_da_erro(bridge):
    result = bridge.save_llm_config("gemini", "")

    assert result["ok"] is False
    assert "chave" in result["error"].lower()


def test_save_llm_config_provedor_desconhecido(bridge):
    result = bridge.save_llm_config("provedor-que-nao-existe", "abc")

    assert result["ok"] is False


def test_save_llm_config_salva_e_recarrega(bridge, tmp_path, monkeypatch):
    import config.settings as settings_module

    monkeypatch.setattr(settings_module, "BASE_DIR", tmp_path)
    (tmp_path / ".env").write_text("LLM_PROVIDER=claude\n", encoding="utf-8")

    result = bridge.save_llm_config("gemini", "minha-chave-de-teste")

    assert result["ok"] is True
    content = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "LLM_PROVIDER=gemini" in content
    assert "GEMINI_API_KEY=minha-chave-de-teste" in content
    assert settings_module.settings.llm_provider == "gemini"


def test_on_window_closing_sem_bandeja_desliga_o_agente(bridge):
    should_close = bridge.on_window_closing()

    assert should_close is True
