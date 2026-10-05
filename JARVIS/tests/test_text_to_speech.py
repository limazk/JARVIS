"""
Testes da cadeia de fallback do TTS (voice/text_to_speech.py::speak).

Bug real corrigido aqui: quando o provedor configurado era o próprio
Edge TTS (padrão do Jarvis) e ele falhava — como aconteceu de verdade
com o erro "403 Invalid response status" quando a Microsoft muda a
validação do serviço —, o Jarvis ficava mudo (a checagem antiga
excluía justamente o caso "Edge falhou" do fallback). Agora cai pro
pyttsx3 (100% offline, sempre funciona) nesse caso.
"""
from __future__ import annotations

from pathlib import Path

from voice import text_to_speech as tts
from voice.audio_player import player as audio_player


def test_provedor_configurado_funciona_toca_normal(monkeypatch):
    played = {}

    class _FakeProvider(tts.TTSProvider):
        def synthesize(self, text):
            return Path("/tmp/fake.mp3")

    monkeypatch.setattr(tts, "get_tts_provider", lambda: _FakeProvider())
    monkeypatch.setattr(audio_player, "play", lambda path, blocking=True: played.update(path=path, blocking=blocking))

    tts.speak("oi", blocking=False)

    assert played == {"path": "/tmp/fake.mp3", "blocking": False}


def test_edge_falha_cai_direto_pro_pyttsx3_sem_tentar_edge_de_novo(monkeypatch):
    calls = []

    monkeypatch.setattr(tts, "get_tts_provider", lambda: tts.EdgeTTSProvider())
    monkeypatch.setattr(tts.EdgeTTSProvider, "synthesize", lambda self, text: (calls.append("edge"), None)[1])
    monkeypatch.setattr(tts.Pyttsx3Provider, "synthesize", lambda self, text: (calls.append("pyttsx3"), None)[1])
    monkeypatch.setattr(audio_player, "play", lambda *a, **k: calls.append("play"))

    tts.speak("oi")

    # Edge chamado só 1x (o provedor configurado) — nunca tenta Edge de novo
    # como "fallback de si mesmo" — e cai pro pyttsx3 sem tocar nada pelo player.
    assert calls == ["edge", "pyttsx3"]


def test_elevenlabs_falha_tenta_edge_e_depois_pyttsx3(monkeypatch):
    calls = []

    monkeypatch.setattr(tts, "get_tts_provider", lambda: tts.ElevenLabsProvider())
    monkeypatch.setattr(tts.ElevenLabsProvider, "synthesize", lambda self, text: (calls.append("elevenlabs"), None)[1])
    monkeypatch.setattr(tts.EdgeTTSProvider, "synthesize", lambda self, text: (calls.append("edge"), None)[1])
    monkeypatch.setattr(tts.Pyttsx3Provider, "synthesize", lambda self, text: (calls.append("pyttsx3"), None)[1])
    monkeypatch.setattr(audio_player, "play", lambda *a, **k: calls.append("play"))

    tts.speak("oi")

    assert calls == ["elevenlabs", "edge", "pyttsx3"]


def test_elevenlabs_falha_mas_edge_funciona_nao_chega_no_pyttsx3(monkeypatch):
    calls = []

    monkeypatch.setattr(tts, "get_tts_provider", lambda: tts.ElevenLabsProvider())
    monkeypatch.setattr(tts.ElevenLabsProvider, "synthesize", lambda self, text: (calls.append("elevenlabs"), None)[1])
    monkeypatch.setattr(tts.EdgeTTSProvider, "synthesize", lambda self, text: (calls.append("edge"), Path("/tmp/edge.mp3"))[1])
    monkeypatch.setattr(tts.Pyttsx3Provider, "synthesize", lambda self, text: (calls.append("pyttsx3"), None)[1])
    monkeypatch.setattr(audio_player, "play", lambda *a, **k: calls.append("play"))

    tts.speak("oi")

    assert calls == ["elevenlabs", "edge", "play"]


def test_pyttsx3_configurado_e_falha_nao_tenta_mais_nada(monkeypatch):
    calls = []

    monkeypatch.setattr(tts, "get_tts_provider", lambda: tts.Pyttsx3Provider())
    monkeypatch.setattr(tts.Pyttsx3Provider, "synthesize", lambda self, text: (calls.append("pyttsx3"), None)[1])
    monkeypatch.setattr(tts.EdgeTTSProvider, "synthesize", lambda self, text: (calls.append("edge"), None)[1])
    monkeypatch.setattr(audio_player, "play", lambda *a, **k: calls.append("play"))

    tts.speak("oi")

    assert calls == ["pyttsx3"]
