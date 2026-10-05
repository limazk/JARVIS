"""
Testes do microfone (voice/listener.py) — cobre um bug real: antes,
uma falha ao abrir o microfone (mesmo passageira, ex.: o driver de
áudio do Windows ainda inicializando bem na hora em que o Jarvis abre
sozinho com o computador) marcava o microfone como indisponível PARA
SEMPRE pelo resto daquela execução — mesmo que o microfone estivesse
funcionando normal segundos depois. Agora só espera um cooldown curto
antes de tentar de novo.
"""
from __future__ import annotations

import sys
import types

import pytest

from voice.listener import MicrophoneListener, feedback_message


def _install_fake_speech_recognition(fail_times: int):
    """
    Injeta um `speech_recognition` fake cujo Microphone() falha as
    primeiras `fail_times` vezes que for usado como context manager, e
    funciona normalmente depois disso.
    """
    fake = types.ModuleType("speech_recognition")
    state = {"attempts": 0}

    class _FakeMicrophone:
        def __enter__(self):
            state["attempts"] += 1
            if state["attempts"] <= fail_times:
                raise OSError("dispositivo de áudio indisponível (simulado)")
            return self

        def __exit__(self, *exc):
            return False

    class _FakeRecognizer:
        def adjust_for_ambient_noise(self, source, duration=0.5):
            pass

        def listen(self, source, timeout=None, phrase_time_limit=None):
            return "audio-fake"

    fake.Microphone = _FakeMicrophone
    fake.Recognizer = _FakeRecognizer

    class WaitTimeoutError(Exception):
        pass

    fake.WaitTimeoutError = WaitTimeoutError
    sys.modules["speech_recognition"] = fake
    return fake, state


@pytest.fixture
def _fake_sr():
    yield
    sys.modules.pop("speech_recognition", None)


def test_is_ready_true_quando_microfone_funciona(_fake_sr):
    _install_fake_speech_recognition(fail_times=0)
    listener = MicrophoneListener()

    assert listener.is_ready() is True


def test_falha_passageira_nao_trava_pra_sempre(monkeypatch, _fake_sr):
    """
    O bug real: antes, essa mesma sequência (falha uma vez, depois o
    cooldown passar, depois funcionar) continuava retornando False pro
    resto da execução — agora, passado o cooldown, tenta de novo e
    reconhece que o microfone está OK.
    """
    _install_fake_speech_recognition(fail_times=1)
    listener = MicrophoneListener()

    fake_time = [1000.0]
    import voice.listener as listener_mod
    monkeypatch.setattr(listener_mod.time, "monotonic", lambda: fake_time[0])

    assert listener.is_ready() is False  # primeira tentativa falha

    fake_time[0] += 5.0  # ainda dentro do cooldown
    assert listener.is_ready() is False  # não tenta de novo tão cedo (evita martelar)

    fake_time[0] += 20.0  # cooldown expirou
    assert listener.is_ready() is True  # tenta de novo e funciona


def test_falha_permanente_continua_reportando_indisponivel(monkeypatch, _fake_sr):
    _install_fake_speech_recognition(fail_times=999)  # nunca funciona
    listener = MicrophoneListener()

    fake_time = [0.0]
    import voice.listener as listener_mod
    monkeypatch.setattr(listener_mod.time, "monotonic", lambda: fake_time[0])

    assert listener.is_ready() is False

    fake_time[0] += 100.0
    assert listener.is_ready() is False  # continua falhando de verdade — não devia "consertar sozinho"


def test_uma_vez_pronto_nao_reabre_o_microfone_de_novo(_fake_sr):
    _fake_module, state = _install_fake_speech_recognition(fail_times=0)
    listener = MicrophoneListener()

    assert listener.is_ready() is True
    assert listener.is_ready() is True

    assert state["attempts"] == 1  # não reabre o microfone a cada checagem


def test_listen_once_detailed_distingue_sem_fala_de_nao_entendido(monkeypatch, _fake_sr):
    """
    O bug real reportado: `listen_once()` devolvia None tanto quando
    ninguém falou nada (timeout) quanto quando falou mas o STT não
    entendeu — fazendo os dois casos parecerem "o microfone não
    funciona". `listen_once_detailed()` diferencia os dois.
    """
    fake, _ = _install_fake_speech_recognition(fail_times=0)

    class _TimeoutRecognizer(fake.Recognizer):
        def listen(self, source, timeout=None, phrase_time_limit=None):
            raise fake.WaitTimeoutError()

    fake.Recognizer = _TimeoutRecognizer
    listener = MicrophoneListener()

    outcome = listener.listen_once_detailed(phrase_time_limit=3)
    assert outcome.text is None
    assert outcome.reason == "no_speech"
    assert "Não ouvi nada" in feedback_message(outcome)


def test_listen_once_detailed_fala_nao_entendida(monkeypatch, _fake_sr):
    import voice.listener as listener_mod

    _install_fake_speech_recognition(fail_times=0)
    monkeypatch.setattr(listener_mod, "get_stt_provider", lambda: types.SimpleNamespace(transcribe=lambda audio: None))
    listener = MicrophoneListener()

    outcome = listener.listen_once_detailed(phrase_time_limit=3)

    assert outcome.text is None
    assert outcome.reason == "not_understood"
    assert "não consegui entender" in feedback_message(outcome).lower()


def test_listen_once_detailed_sucesso_nao_tem_mensagem_de_erro(monkeypatch, _fake_sr):
    import voice.listener as listener_mod

    _install_fake_speech_recognition(fail_times=0)
    monkeypatch.setattr(
        listener_mod, "get_stt_provider", lambda: types.SimpleNamespace(transcribe=lambda audio: "liga o spotify")
    )
    listener = MicrophoneListener()

    outcome = listener.listen_once_detailed(phrase_time_limit=3)

    assert outcome.text == "liga o spotify"
    assert outcome.reason == "ok"
    assert feedback_message(outcome) is None

    # `listen_once` continua funcionando como antes (só o texto).
    assert listener.listen_once(phrase_time_limit=3) == "liga o spotify"


def test_listen_once_concorrente_nao_quebra_o_microfone_compartilhado(monkeypatch, _fake_sr):
    """
    Bug real corrigido: com a voz contínua ligada, o loop de detecção de
    wake word (voice/wake_word.py, rodando na sua própria thread) e o
    botão de microfone manual da interface (interface/app.py::_handle_mic,
    rodando em outra thread) podiam chamar listener.listen_once() ao mesmo
    tempo no mesmo `MicrophoneListener` compartilhado. A lib
    speech_recognition não permite dois `with microphone:` abertos ao
    mesmo tempo — antes dessa correção isso quebrava com "This audio
    source is already inside a context manager". Agora a segunda chamada
    concorrente desiste de bater (devolve None) em vez de quebrar.
    """
    import threading

    import voice.listener as listener_mod

    _install_fake_speech_recognition(fail_times=0)
    listener = MicrophoneListener()
    assert listener.is_ready() is True

    monkeypatch.setattr(
        listener_mod, "get_stt_provider", lambda: types.SimpleNamespace(transcribe=lambda audio: "comando falado")
    )

    entered = threading.Event()
    release = threading.Event()

    import speech_recognition as sr

    def _slow_listen(self, source, timeout=None, phrase_time_limit=None):
        entered.set()
        release.wait(timeout=2)
        return "audio-fake"

    monkeypatch.setattr(sr.Recognizer, "listen", _slow_listen)

    results = {}

    def _first_call():
        results["first"] = listener.listen_once()

    t = threading.Thread(target=_first_call)
    t.start()
    assert entered.wait(timeout=2)  # espera a primeira chamada estar "gravando"

    # Segunda chamada concorrente: não deve quebrar, só desistir com None.
    second_result = listener.listen_once()
    assert second_result is None

    release.set()
    t.join(timeout=2)
    assert results["first"] == "comando falado"
