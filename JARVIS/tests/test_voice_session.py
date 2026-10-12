"""Regression tests: after wake word, errors must not be silent."""
from voice.listener import ListenOutcome
from voice.session import capture_command


class StubListener:
    def __init__(self, *outcomes):
        self._items = iter(outcomes)
        self.calls = 0

    def listen_once_detailed(self, phrase_time_limit=None):
        self.calls += 1
        assert phrase_time_limit == 12
        return next(self._items)


def test_capture_first_try_returns_text():
    listener = StubListener(ListenOutcome("que horas são", "ok"))
    assert capture_command(listener, phrase_time_limit=12) == "que horas são"
    assert listener.calls == 1


def test_silence_warns_and_retries_once(capsys):
    listener = StubListener(
        ListenOutcome(None, "no_speech"),
        ListenOutcome("me explica sua memória", "ok"),
    )
    prompts = []
    result = capture_command(listener, phrase_time_limit=12, on_retry=prompts.append)
    assert result == "me explica sua memória"
    assert listener.calls == 2
    assert prompts == ["Não ouvi sua pergunta. Pode repetir?"]
    assert "[escuta: no_speech]" in capsys.readouterr().out


def test_unrecognized_audio_retries_once(capsys):
    listener = StubListener(
        ListenOutcome(None, "not_understood"),
        ListenOutcome(None, "not_understood"),
    )
    assert capture_command(listener, phrase_time_limit=12) is None
    assert listener.calls == 2
    assert "not_understood" in capsys.readouterr().out


def test_unavailable_microphone_does_not_repeat_or_call_ai(capsys):
    listener = StubListener(ListenOutcome(None, "mic_unavailable"))
    assert capture_command(listener, phrase_time_limit=12) is None
    assert listener.calls == 1
    assert "mic_unavailable" in capsys.readouterr().out


def test_busy_microphone_does_not_loop_forever(capsys):
    listener = StubListener(ListenOutcome(None, "mic_busy"))
    assert capture_command(listener, phrase_time_limit=12) is None
    assert listener.calls == 1
    assert "mic_busy" in capsys.readouterr().out


def test_spoken_retry_failure_still_attempts_audio_again():
    listener = StubListener(
        ListenOutcome(None, "no_speech"),
        ListenOutcome("ok", "ok"),
    )
    def failing_voice(_prompt):
        raise RuntimeError("tts unavailable")
    assert capture_command(listener, phrase_time_limit=12, on_retry=failing_voice) == "ok"
    assert listener.calls == 2
