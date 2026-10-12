"""Falha Edge 403 deve cair em voz offline segura quando eSpeak está instalado."""
from pathlib import Path
from types import SimpleNamespace

from config.settings import settings
from voice import text_to_speech as tts
from voice.audio_player import player


def test_espeak_generates_wav_without_shell(monkeypatch, tmp_path):
    called = {}
    monkeypatch.setattr(tts.platform, "system", lambda: "Linux")
    monkeypatch.setattr(tts.shutil, "which", lambda name: "/usr/bin/espeak-ng" if name == "espeak-ng" else None)
    monkeypatch.setattr(tts.tempfile, "mkstemp", lambda **kw: _tempfile_wav(tmp_path))

    def fake_run(cmd, **kwargs):
        called["command"] = cmd
        called["kwargs"] = kwargs
        kwargs["stdout"].write(b"RIFF" + b"0" * 64)
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr(tts.subprocess, "run", fake_run)
    wav = tts.EspeakProvider().synthesize("Boa noite")
    assert wav is not None and wav.suffix == ".wav"
    assert called["command"][:2] == ["/usr/bin/espeak-ng", "-v"]
    assert called["kwargs"]["input"] == "Boa noite".encode()
    assert called["kwargs"]["check"] is False
    assert called["kwargs"]["timeout"] == 30


def _tempfile_wav(tmp_path):
    import os
    return os.open(tmp_path / "test.wav", os.O_CREAT | os.O_RDWR, 0o600), str(tmp_path / "test.wav")


def test_espeak_is_preferred_over_broken_pyttsx3(monkeypatch):
    events = []
    monkeypatch.setattr(tts, "get_tts_provider", lambda: tts.EdgeTTSProvider())
    monkeypatch.setattr(tts.EdgeTTSProvider, "synthesize", lambda self, text: (events.append("edge403"), None)[1])
    monkeypatch.setattr(tts.EspeakProvider, "synthesize", lambda self, text: (events.append("espeak"), Path("/tmp/espeak.wav"))[1])
    monkeypatch.setattr(tts.Pyttsx3Provider, "synthesize", lambda self, text: events.append("pyttsx3"))
    monkeypatch.setattr(player, "play", lambda path, blocking=True: events.append(("play", path)))
    tts.speak("teste", blocking=True)
    assert events == ["edge403", "espeak", ("play", "/tmp/espeak.wav")]


def test_espeak_can_be_selected_explicitly(monkeypatch):
    monkeypatch.setattr(settings, "tts_provider", "espeak")
    assert isinstance(tts.get_tts_provider(), tts.EspeakProvider)


def test_missing_espeak_falls_back_to_pyttsx3(monkeypatch):
    events = []
    monkeypatch.setattr(tts, "get_tts_provider", lambda: tts.EdgeTTSProvider())
    monkeypatch.setattr(tts.EdgeTTSProvider, "synthesize", lambda self, text: (events.append("edge"), None)[1])
    monkeypatch.setattr(tts.EspeakProvider, "synthesize", lambda self, text: (events.append("espeak_missing"), None)[1])
    monkeypatch.setattr(tts.Pyttsx3Provider, "synthesize", lambda self, text: events.append("pyttsx3"))
    tts.speak("teste")
    assert events == ["edge", "espeak_missing", "pyttsx3"]
