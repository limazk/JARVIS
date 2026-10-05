"""
Bot do Discord — outra "interface" pro mesmo JarvisAgent (como o modo
texto, o modo voz e a GUI), pra dar pra mandar comando pro Jarvis de
fora do PC (ex.: do celular, pelo app do Discord). Item pedido do
roadmap ("Discord como bot/webhook").

Segurança: só responde a mensagens DIRETAS (DM) vindas do
DISCORD_OWNER_ID configurado no .env — qualquer outra pessoa, ou
mensagem mandada num servidor/canal, é ignorada silenciosamente. Isso
importa porque o Jarvis tem ferramentas de risco alto (terminal,
bloquear o PC, apagar arquivo, etc.) — não dá pra deixar qualquer um
que ache o bot no Discord mandar comando pro seu computador.

Como configurar (veja também o README, seção "Bot do Discord"):
1. https://discord.com/developers/applications -> "New Application"
2. Aba "Bot" (barra lateral) -> "Reset Token"/"Copy" -> cole em
   DISCORD_BOT_TOKEN no .env
3. Ainda na aba "Bot", em "Privileged Gateway Intents", ative
   "MESSAGE CONTENT INTENT" e salve — sem isso o bot recebe a mensagem
   mas não consegue ler o texto dela.
4. Aba "OAuth2" -> "URL Generator" -> marque o escopo "bot" ->
   permissões "Send Messages" + "Read Message History" -> abra o link
   gerado e adicione o bot a um servidor seu (o Discord só permite
   mandar DM pra um bot que compartilha um servidor com você — pode
   ser um servidor privado, só seu, criado na hora pra isso).
5. No Discord, ative o "Modo desenvolvedor" (Configurações do usuário
   -> Avançado) pra poder clicar com o botão direito no seu próprio
   nome -> "Copiar ID do Usuário" -> cole em DISCORD_OWNER_ID no .env.

Depois disso: `python main.py --discord` deixa o bot rodando (Ctrl+C
pra encerrar), e é só mandar uma DM pra ele pelo Discord do celular ou
do PC.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Optional

from config.settings import settings

logger = logging.getLogger("jarvis.discord_bot")

_DISCORD_MAX_LEN = 2000  # limite de caracteres numa única mensagem do Discord
_CONFIRM_WORDS = {"sim", "s", "yes", "y"}


def _split_for_discord(text: str) -> list[str]:
    """Discord recusa mensagens com mais de 2000 caracteres — quebra em pedaços."""
    text = text or "..."
    if len(text) <= _DISCORD_MAX_LEN:
        return [text]
    return [text[i : i + _DISCORD_MAX_LEN] for i in range(0, len(text), _DISCORD_MAX_LEN)]


def run_discord_bot() -> None:
    try:
        import discord
    except ImportError:
        print(
            "O modo Discord requer o pacote discord.py (pip install discord.py). "
            "Use: python main.py --text"
        )
        return

    if not settings.discord_bot_token:
        print(
            "Falta DISCORD_BOT_TOKEN no .env. Veja o topo de interface/discord_bot.py "
            "ou o README (seção 'Bot do Discord') para o passo a passo."
        )
        return
    if not settings.discord_owner_id:
        print(
            "Falta DISCORD_OWNER_ID no .env (o ID numérico da sua conta do Discord — sem "
            "ele, o bot não sabe em quem confiar e ignora todo mundo por segurança). "
            "Veja o README (seção 'Bot do Discord')."
        )
        return
    try:
        owner_id = int(settings.discord_owner_id)
    except ValueError:
        print("DISCORD_OWNER_ID precisa ser só números (o ID numérico da sua conta do Discord).")
        return

    from core.agent import JarvisAgent

    intents = discord.Intents.default()
    intents.message_content = True
    intents.dm_messages = True
    client = discord.Client(intents=intents)

    # Processa uma mensagem de cada vez: evita duas DMs quase simultâneas
    # disputando o mesmo `agent.permissions.confirm_callback` (reatribuído
    # a cada mensagem, ver `_worker` abaixo).
    _process_lock = threading.Lock()
    _state: dict = {}  # guarda o JarvisAgent (criado só depois de conectar — ver on_ready)

    def _confirm_via_discord(channel_id: int, message_text: str) -> bool:
        """
        Ponte síncrona -> assíncrona: o PermissionManager espera uma
        função comum (mesmo contrato do modo texto/voz/GUI) que devolve
        True/False. Essa função roda numa thread de trabalho (run_in_executor
        no on_message), então pedir confirmação aqui significa agendar uma
        coroutine no loop de eventos do Discord e bloquear essa thread até
        a resposta chegar — mesma ideia do `_confirm_dialog` da GUI
        (interface/app.py), só que com asyncio em vez de threading.Event.
        """

        async def _ask() -> bool:
            channel = client.get_channel(channel_id) or await client.fetch_channel(channel_id)
            await channel.send(f"⚠️ {message_text}\nResponda **sim** ou **não** (2 minutos).")

            def _check(m: "discord.Message") -> bool:
                return m.channel.id == channel_id and m.author.id == owner_id

            try:
                reply = await client.wait_for("message", check=_check, timeout=115)
            except asyncio.TimeoutError:
                return False
            return reply.content.strip().lower() in _CONFIRM_WORDS

        try:
            return asyncio.run_coroutine_threadsafe(_ask(), client.loop).result(timeout=125)
        except Exception:
            return False

    def _on_reminder_due(message: str) -> None:
        """Chamado pelo ReminderScheduler numa thread própria (não-async) — mesma ponte de cima."""

        async def _send() -> None:
            user = client.get_user(owner_id) or await client.fetch_user(owner_id)
            dm = user.dm_channel or await user.create_dm()
            for chunk in _split_for_discord(message):
                await dm.send(chunk)

        try:
            asyncio.run_coroutine_threadsafe(_send(), client.loop).result(timeout=30)
        except Exception:
            logger.exception("Não consegui mandar o lembrete pelo Discord.")

    @client.event
    async def on_ready() -> None:
        if "agent" not in _state:
            _state["agent"] = JarvisAgent(on_reminder_due=_on_reminder_due)
        print(f"[Discord] Conectado como {client.user}. Mande uma DM para conversar com o {settings.jarvis_name}.")

    @client.event
    async def on_message(message: "discord.Message") -> None:
        if client.user is not None and message.author.id == client.user.id:
            return
        if message.author.id != owner_id:
            return  # ignora qualquer um que não seja o dono (ver "Segurança" no topo do arquivo)
        if message.guild is not None:
            return  # só responde em DM, nunca em canal de servidor
        text = message.content.strip()
        if not text:
            return

        agent = _state.get("agent")
        if agent is None:
            return  # ainda conectando — on_ready não rodou ainda

        loop = asyncio.get_running_loop()

        def _worker() -> str:
            with _process_lock:
                agent.permissions.confirm_callback = lambda msg: _confirm_via_discord(message.channel.id, msg)
                return agent.process(text)

        async with message.channel.typing():
            reply = await loop.run_in_executor(None, _worker)

        for chunk in _split_for_discord(reply):
            await message.channel.send(chunk)

    print(f"\n{settings.jarvis_name.upper()} — modo Discord. Ctrl+C para encerrar.\n")
    for warning in settings.validate():
        print(f"[aviso] {warning}")

    try:
        client.run(settings.discord_bot_token, log_handler=None)
    except Exception as exc:
        print(f"Não consegui conectar ao Discord: {exc}")
    finally:
        agent = _state.get("agent")
        if agent is not None:
            agent.shutdown()
