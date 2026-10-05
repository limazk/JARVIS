"""
Testes do modo "sempre ouvindo" (voice/wake_word.py e main.py::_wake_greeting).

`openwakeword`/`pyaudio` reais não são necessários aqui: o caminho via
openWakeWord é testado injetando módulos fake em sys.modules (mesmo
padrão usado em test_spotify.py/test_discord_bot.py para libs opcionais
não disponíveis neste sandbox), e o caminho de fallback é testado
monkeypatchando `voice.listener.listener` diretamente.
"""
from __future__ import annotations

import sys
import types

import pytest

from config.settings import settings


def test_wake_greeting_usa_user_title(monkeypatch):
    import main

    monkeypatch.setattr(settings, "wake_greeting", "")
    monkeypatch.setattr(settings, "user_title", "Senhor")

    assert main._wake_greeting() == "Sim, Senhor. O que deseja?"


def test_wake_greeting_sem_user_title(monkeypatch):
    import main

    monkeypatch.setattr(settings, "wake_greeting", "")
    monkeypatch.setattr(settings, "user_title", "")

    assert main._wake_greeting() == "Sim? O que deseja?"


def test_wake_greeting_customizada_tem_prioridade(monkeypatch):
    import main

    monkeypatch.setattr(settings, "wake_greeting", "Pois não, chefe?")
    monkeypatch.setattr(settings, "user_title", "Senhor")

    assert main._wake_greeting() == "Pois não, chefe?"


def test_sem_openwakeword_instalado_usa_fallback(monkeypatch):
    """Sem a lib instalada (caso comum, já que é uma dependência opcional),
    o detector precisa cair no modo de fallback em vez de quebrar."""
    from voice import wake_word

    monkeypatch.setattr(wake_word.WakeWordDetector, "_openwakeword_available", staticmethod(lambda: False))

    calls = []
    detector = wake_word.WakeWordDetector(on_wake=lambda: calls.append(1))
    monkeypatch.setattr(detector, "_run_fallback", lambda: calls.append("fallback"))
    monkeypatch.setattr(detector, "_run_openwakeword", lambda: calls.append("openwakeword"))

    detector.start()
    detector._thread.join(timeout=2)

    assert calls == ["fallback"]


def test_fallback_dispara_on_wake_quando_ouve_a_wake_word(monkeypatch):
    from voice import listener as listener_mod
    from voice import wake_word

    monkeypatch.setattr(settings, "wake_word", "jarvis")

    textos = iter(["oi tudo bem", "jarvis, que horas são", None])

    def _fake_listen_once(phrase_time_limit=None):
        return next(textos, None)

    monkeypatch.setattr(listener_mod.listener, "listen_once", _fake_listen_once)

    detector = wake_word.WakeWordDetector(on_wake=lambda: detector.stop())
    detector._run_fallback()  # roda direto (síncrono) — só 3 iterações no fake acima


def test_run_fallback_espera_on_wake_terminar_antes_de_ouvir_de_novo(monkeypatch):
    """
    Bug real corrigido: a versão anterior de `interface/app.py` processava
    o comando (saudação + escuta + resposta) numa thread separada e
    retornava na hora — o loop de detecção aqui embaixo não esperava isso
    terminar, e voltava a chamar listener.listen_once() em paralelo,
    disputando o mesmo microfone com a captura do comando (o erro era
    "'NoneType' object does not support the context manager protocol",
    repetido centenas de vezes por segundo). Esse teste garante o
    invariante do qual a correção depende: o loop SÓ chama listen_once()
    de novo depois que on_wake() retornar de verdade.
    """
    from voice import listener as listener_mod
    from voice import wake_word

    monkeypatch.setattr(settings, "wake_word", "jarvis")

    calls: list[str] = []
    textos = iter(["jarvis", "jarvis"])
    listens_since_last_wake = [0]

    def _fake_listen_once(phrase_time_limit=None):
        calls.append("listen")
        listens_since_last_wake[0] += 1
        return next(textos, None)

    monkeypatch.setattr(listener_mod.listener, "listen_once", _fake_listen_once)

    detector = wake_word.WakeWordDetector(on_wake=lambda: None)

    def _slow_on_wake() -> None:
        # Se o loop tivesse voltado a chamar listen_once() antes de on_wake()
        # terminar a rodada anterior (o bug real corrigido), esse contador
        # estaria em 2+ em vez de exatamente 1 aqui.
        calls.append("on_wake_start")
        assert listens_since_last_wake[0] == 1
        listens_since_last_wake[0] = 0
        calls.append("on_wake_end")
        if calls.count("on_wake_start") >= 2:
            detector.stop()

    detector.on_wake = _slow_on_wake
    detector._run_fallback()

    assert calls == ["listen", "on_wake_start", "on_wake_end", "listen", "on_wake_start", "on_wake_end"]


def test_run_fallback_pausa_em_vez_de_martelar_quando_fica_sem_resposta(monkeypatch):
    """
    Rede de segurança contra loop apertado: se listener.listen_once ficar
    voltando None rapidamente (ex.: microfone com problema, durante o
    cooldown de retry de voice/listener.py), o loop precisa pausar em vez
    de girar no máximo da CPU enchendo o log de erro sem parar.
    """
    from voice import listener as listener_mod
    from voice import wake_word

    monkeypatch.setattr(settings, "wake_word", "jarvis")
    monkeypatch.setattr(listener_mod.listener, "listen_once", lambda phrase_time_limit=None: None)

    sleep_calls = []
    detector = wake_word.WakeWordDetector(on_wake=lambda: None)

    def _fake_sleep(seconds):
        sleep_calls.append(seconds)
        if len(sleep_calls) >= 3:
            detector.stop()

    monkeypatch.setattr(wake_word.time, "sleep", _fake_sleep)

    detector._run_fallback()

    assert sleep_calls == [0.5, 0.5, 0.5]


def test_openwakeword_detecta_e_chama_on_wake(monkeypatch):
    """
    Injeta módulos fake pra `openwakeword`, `pyaudio` e `numpy` (numpy real
    pode não estar disponível neste sandbox de testes) e confirma que, ao
    ver um score alto pro modelo "hey_jarvis", o detector chama on_wake()
    e depois respeita o cooldown (não dispara de novo pro frame seguinte).
    """
    from voice import wake_word

    # --- numpy fake mínimo (só o que wake_word.py usa: np.frombuffer) ---
    fake_np = types.ModuleType("numpy")
    fake_np.int16 = "int16"
    fake_np.frombuffer = lambda data, dtype=None: data
    sys.modules["numpy"] = fake_np

    # --- pyaudio fake ---
    fake_pyaudio = types.ModuleType("pyaudio")
    fake_pyaudio.paInt16 = 8

    class _FakeStream:
        def __init__(self, frames):
            self._frames = list(frames)

        def read(self, chunk, exception_on_overflow=False):
            if not self._frames:
                raise RuntimeError("_StopTest")
            return self._frames.pop(0)

        def stop_stream(self):
            pass

        def close(self):
            pass

    class _FakePyAudio:
        def __init__(self):
            self.stream = _FakeStream([b"frame-baixo", b"frame-wake", b"frame-depois-do-cooldown"])

        def open(self, **kwargs):
            return self.stream

        def terminate(self):
            pass

    fake_pyaudio.PyAudio = _FakePyAudio
    sys.modules["pyaudio"] = fake_pyaudio

    # --- openwakeword fake ---
    fake_oww = types.ModuleType("openwakeword")
    fake_oww.utils = types.SimpleNamespace(download_models=lambda names: None)
    fake_model_mod = types.ModuleType("openwakeword.model")

    scores = iter([0.1, 0.9, 0.9])  # baixo, dispara, ainda alto mas em cooldown

    class _FakeModel:
        def __init__(self, wakeword_models=None):
            self.wakeword_models = wakeword_models

        def predict(self, frame):
            return {"hey_jarvis": next(scores, 0.0)}

    fake_model_mod.Model = _FakeModel
    sys.modules["openwakeword"] = fake_oww
    sys.modules["openwakeword.model"] = fake_model_mod

    try:
        calls = []
        detector = wake_word.WakeWordDetector(on_wake=lambda: calls.append(1))
        assert detector._openwakeword_available() is True

        with pytest.raises(RuntimeError, match="_StopTest"):
            detector._run_openwakeword()

        # 1º frame: score baixo (não dispara). 2º frame: score alto -> dispara.
        # 3º frame: score alto de novo, mas ainda dentro do cooldown -> não dispara.
        assert calls == [1]
    finally:
        for mod in ("numpy", "pyaudio", "openwakeword", "openwakeword.model"):
            sys.modules.pop(mod, None)
