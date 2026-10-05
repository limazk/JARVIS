"""
Testes do player de áudio (voice/audio_player.py) — cobre um bug real
visto em produção no Windows: `pygame.mixer.music.load()` mantém o
arquivo de áudio anterior aberto/travado até outro arquivo ser
carregado ou `unload()` ser chamado explicitamente. Como o Jarvis
sempre grava a fala em cima do MESMO nome de arquivo temporário
(voice/text_to_speech.py), a próxima fala tentava sobrescrever um
arquivo que o Windows ainda considerava "em uso" pelo pygame e
quebrava com `PermissionError: [Errno 13] Permission denied` — nunca
acontecia no Linux/Mac, que deixam sobrescrever arquivos abertos. A
correção chama `unload()` antes de carregar o próximo áudio (e depois
de tocar/parar o atual) pra sempre liberar o arquivo.
"""
from __future__ import annotations

import sys
import types

import pytest


def _install_fake_pygame():
    fake = types.ModuleType("pygame")
    calls: list[str] = []

    class _FakeMusic:
        _busy = False

        @staticmethod
        def load(path):
            calls.append(f"load:{path}")

        @staticmethod
        def play():
            calls.append("play")
            _FakeMusic._busy = True

        @staticmethod
        def stop():
            calls.append("stop")
            _FakeMusic._busy = False

        @staticmethod
        def unload():
            calls.append("unload")

        @staticmethod
        def get_busy():
            # só "toca" por uma checagem, depois já termina sozinho
            was_busy = _FakeMusic._busy
            _FakeMusic._busy = False
            return was_busy

    class _FakeMixer:
        music = _FakeMusic

        @staticmethod
        def init():
            calls.append("init")

    fake.mixer = _FakeMixer
    sys.modules["pygame"] = fake
    return calls


@pytest.fixture
def _fake_pygame():
    calls = _install_fake_pygame()
    yield calls
    sys.modules.pop("pygame", None)


def test_play_libera_o_arquivo_anterior_antes_de_carregar_o_proximo(_fake_pygame):
    from voice.audio_player import AudioPlayer

    player = AudioPlayer()
    player.play("primeira_fala.mp3", blocking=True)
    player.play("segunda_fala.mp3", blocking=True)

    # unload() precisa acontecer ANTES de cada load() (libera o arquivo
    # anterior) — sem isso, no Windows a 2ª fala quebrava tentando
    # sobrescrever um arquivo que o pygame ainda tinha aberto.
    assert _fake_pygame == [
        "init",
        "unload",
        "load:primeira_fala.mp3",
        "play",
        "unload",  # liberado ao final da reprodução (bloqueante)
        "unload",
        "load:segunda_fala.mp3",
        "play",
        "unload",
    ]


def test_stop_tambem_libera_o_arquivo(_fake_pygame):
    from voice.audio_player import AudioPlayer

    player = AudioPlayer()
    player.play("fala.mp3", blocking=False)
    player.stop()

    assert _fake_pygame == ["init", "unload", "load:fala.mp3", "play", "stop", "unload"]


def test_unload_ausente_nao_quebra_o_player(monkeypatch, _fake_pygame):
    """Se por algum motivo `unload` não existir (ex.: pygame original, sem
    o método), o player precisa continuar funcionando normalmente."""
    import pygame

    monkeypatch.delattr(pygame.mixer.music, "unload")

    from voice.audio_player import AudioPlayer

    player = AudioPlayer()
    player.play("fala.mp3", blocking=True)  # não deve levantar exceção
