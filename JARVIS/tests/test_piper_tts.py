"""Regression tests for offline Brazilian Piper TTS."""
import json
import os
from pathlib import Path
from types import SimpleNamespace

from config.settings import settings
from voice import piper_engine
from voice import text_to_speech as tts
from voice.audio_player import player


def _configure(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "base_dir", tmp_path)
    monkeypatch.setattr(settings, "piper_bin", "")
    monkeypatch.setattr(settings, "piper_model", "")
    monkeypatch.setattr(settings, "piper_timeout", 30)
    binary = piper_engine.default_bin_path()
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text("fake executable")
    binary.chmod(0o700)
    model = piper_engine.default_model_path()
    model.parent.mkdir(parents=True, exist_ok=True)
    model.write_bytes(b"x" * 1_000_020)
    Path(str(model) + ".json").write_text(json.dumps({"language": {"code": "pt_BR"}}))
    return binary, model


def test_model_required_before_any_synthesis(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "base_dir", tmp_path)
    monkeypatch.setattr(settings, "piper_bin", "")
    monkeypatch.setattr(settings, "piper_model", "")
    assert not piper_engine.piper_status()[0]
    assert piper_engine.synthesize_piper("ola") is None


def test_piper_renders_valid_wav_via_cli(monkeypatch, tmp_path):
    binary, model = _configure(monkeypatch, tmp_path)
    captured = {}

    def fake_run(argv, **kwargs):
        captured.update(argv=argv, kwargs=kwargs)
        Path(argv[argv.index("--output_file") + 1]).write_bytes(
            b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 36
        )
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr(piper_engine.subprocess, "run", fake_run)
    wav = piper_engine.synthesize_piper("Olá, voz brasileira!")
    assert wav and wav.exists()
    assert captured["argv"][0] == str(binary)
    assert captured["argv"][2] == str(model.resolve())
    assert captured["kwargs"]["input"] == "Olá, voz brasileira!".encode()
    assert captured["kwargs"]["timeout"] == 30
    assert captured["kwargs"]["cwd"] == str(binary.parent)
    assert "shell" not in captured["kwargs"]
    wav.unlink()


def test_failed_piper_removes_partial_audio(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    out = tmp_path / "partial.wav"
    monkeypatch.setattr(
        piper_engine.tempfile, "mkstemp",
        lambda **kw: (os.open(out, os.O_CREAT | os.O_RDWR, 0o600), str(out)),
    )
    monkeypatch.setattr(
        piper_engine.subprocess, "run",
        lambda *a, **kw: SimpleNamespace(returncode=1, stderr=b"model invalid"),
    )
    assert piper_engine.synthesize_piper("oi") is None
    assert not out.exists()


def test_wrong_language_is_not_accepted(monkeypatch, tmp_path):
    _, model = _configure(monkeypatch, tmp_path)
    Path(str(model) + ".json").write_text('{"language":{"code":"en_US"}}')
    ready, detail = piper_engine.piper_status()
    assert not ready
    assert "pt-BR" in detail


def test_piper_selectable(monkeypatch):
    monkeypatch.setattr(settings, "tts_provider", "piper")
    assert isinstance(tts.get_tts_provider(), tts.PiperTTSProvider)


def test_piper_preferred_over_espeak(monkeypatch):
    calls = []
    monkeypatch.setattr(tts, "get_tts_provider", lambda: tts.PiperTTSProvider())
    monkeypatch.setattr(tts.PiperTTSProvider, "synthesize", lambda self, text: (calls.append("piper"), Path("/tmp/neural.wav"))[1])
    monkeypatch.setattr(tts.EspeakProvider, "synthesize", lambda self, text: calls.append("espeak"))
    monkeypatch.setattr(player, "play", lambda path, blocking=True: calls.append(("play", path)))
    tts.speak("oi")
    assert calls == ["piper", ("play", "/tmp/neural.wav")]


def test_piper_fallback_is_offline(monkeypatch):
    calls = []
    monkeypatch.setattr(tts, "get_tts_provider", lambda: tts.PiperTTSProvider())
    monkeypatch.setattr(tts.PiperTTSProvider, "synthesize", lambda self, text: (calls.append("piper"), None)[1])
    monkeypatch.setattr(tts.EspeakProvider, "synthesize", lambda self, text: (calls.append("espeak"), Path("/tmp/robot.wav"))[1])
    monkeypatch.setattr(tts.EdgeTTSProvider, "synthesize", lambda self, text: calls.append("edge"))
    monkeypatch.setattr(player, "play", lambda path, blocking=True: calls.append(("play", path)))
    tts.speak("oi")
    assert calls == ["piper", "espeak", ("play", "/tmp/robot.wav")]


def test_edge_403_can_fallback_to_piper(monkeypatch):
    calls = []
    monkeypatch.setattr(tts, "get_tts_provider", lambda: tts.EdgeTTSProvider())
    monkeypatch.setattr(tts.EdgeTTSProvider, "synthesize", lambda self, text: (calls.append("edge403"), None)[1])
    monkeypatch.setattr(tts.PiperTTSProvider, "synthesize", lambda self, text: (calls.append("piper"), Path("/tmp/neural.wav"))[1])
    monkeypatch.setattr(tts.EspeakProvider, "synthesize", lambda self, text: calls.append("espeak"))
    monkeypatch.setattr(player, "play", lambda path, blocking=True: calls.append(("play", path)))
    tts.speak("oi")
    assert calls == ["edge403", "piper", ("play", "/tmp/neural.wav")]
