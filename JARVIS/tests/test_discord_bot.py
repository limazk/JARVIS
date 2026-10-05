"""
Testes do bot do Discord (interface/discord_bot.py) — item do roadmap
("Discord como bot/webhook").

`discord.py` não está disponível neste sandbox de testes (sem acesso
ao índice do PyPI), então testamos aqui só o que não depende da
biblioteca de verdade: a função pura de quebra de mensagem e as
checagens de configuração (token/owner id ausentes ou inválidos), que
devem falhar de forma honesta ANTES de qualquer tentativa de conexão
real. Para essas checagens, um módulo `discord` fake mínimo é
injetado em `sys.modules` só pra deixar o `import discord` no topo da
função passar — o teste nunca chega a criar um `discord.Client` de
verdade nem abrir conexão nenhuma.
"""
from __future__ import annotations

import sys
import types

import pytest

from config.settings import settings
from interface.discord_bot import _split_for_discord


def test_split_for_discord_mensagem_curta_fica_inteira():
    assert _split_for_discord("oi") == ["oi"]


def test_split_for_discord_mensagem_vazia_vira_reticencias():
    assert _split_for_discord("") == ["..."]


def test_split_for_discord_quebra_mensagens_longas():
    texto = "a" * 4500
    partes = _split_for_discord(texto)
    assert len(partes) == 3
    assert all(len(p) <= 2000 for p in partes)
    assert "".join(partes) == texto


def test_sem_discord_instalado_avisa_e_nao_quebra():
    sys.modules.pop("discord", None)
    from interface import discord_bot

    discord_bot.run_discord_bot()  # não deve levantar exceção


@pytest.fixture
def _fake_discord_module():
    fake = types.ModuleType("discord")
    sys.modules["discord"] = fake
    yield fake
    sys.modules.pop("discord", None)


def test_sem_token_avisa_e_nao_tenta_conectar(monkeypatch, capsys, _fake_discord_module):
    from interface import discord_bot

    monkeypatch.setattr(settings, "discord_bot_token", "")
    monkeypatch.setattr(settings, "discord_owner_id", "123456")

    discord_bot.run_discord_bot()

    assert "DISCORD_BOT_TOKEN" in capsys.readouterr().out


def test_sem_owner_id_avisa_e_nao_tenta_conectar(monkeypatch, capsys, _fake_discord_module):
    from interface import discord_bot

    monkeypatch.setattr(settings, "discord_bot_token", "um-token-qualquer")
    monkeypatch.setattr(settings, "discord_owner_id", "")

    discord_bot.run_discord_bot()

    assert "DISCORD_OWNER_ID" in capsys.readouterr().out


def test_owner_id_nao_numerico_avisa_e_nao_tenta_conectar(monkeypatch, capsys, _fake_discord_module):
    from interface import discord_bot

    monkeypatch.setattr(settings, "discord_bot_token", "um-token-qualquer")
    monkeypatch.setattr(settings, "discord_owner_id", "nao-e-um-numero")

    discord_bot.run_discord_bot()

    assert "números" in capsys.readouterr().out
