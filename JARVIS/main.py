"""
Ponto de entrada do Jarvis.

Uso (rode sempre a partir da pasta jarvis/, com o venv ativado):
    python main.py             # abre a interface gráfica (a partir da ETAPA 6)
    python main.py --text      # modo texto no terminal
    python main.py --voice     # modo voz contínuo por terminal (ver também o
                                # toggle "Voz contínua" dentro da própria
                                # interface gráfica — não precisa mais disto)
    python main.py --discord   # bot do Discord (conversa por DM, de fora do PC)
    python main.py --minimized # abre a interface direto na bandeja (usado
                                # pelo início automático com o Windows)
    python main.py --background # serviço headless (systemd --user no Linux)
    python main.py --nexus      # abre o orquestrador multiagente NEXUS no terminal
    python main.py --doctor     # diagnóstico sem mostrar segredos
    python main.py --debug     # ativa logs detalhados de intenção/tool/tempo
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Garante que a raiz do projeto está no sys.path, mesmo rodando de outro cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.settings import settings  # noqa: E402


def setup_logging(debug: bool) -> None:
    settings.log_path.parent.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(settings.log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    # Silencia logs de bibliotecas de rede em modo normal.
    if not debug:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)


def run_text_mode() -> None:
    from core.agent import JarvisAgent

    print(f"\n{settings.jarvis_name.upper()} — modo texto. Digite 'sair' para encerrar.\n")

    for warning in settings.validate():
        print(f"[aviso] {warning}")

    agent = JarvisAgent()
    print(f"\n{settings.jarvis_name}: {settings.jarvis_name} online.\n")

    while True:
        try:
            user_text = input("Você: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nEncerrando.")
            break
        if not user_text:
            continue
        if user_text.lower() in {"sair", "exit", "quit"}:
            print(f"{settings.jarvis_name}: Até mais.")
            break
        reply = agent.process(user_text)
        print(f"{settings.jarvis_name}: {reply}")

    agent.shutdown()


def _wake_greeting() -> str:
    """
    Frase falada assim que o Jarvis ouve a wake word, antes de escutar o
    comando de verdade — o "Jarvis" -> "Sim, Senhor. O que deseja?" do modo
    contínuo. Customizável via WAKE_GREETING; se vazio, monta sozinho a
    partir de USER_TITLE (mesma lógica usada no resto do Jarvis).
    """
    if settings.wake_greeting.strip():
        return settings.wake_greeting.strip()
    if settings.user_title.strip():
        return f"Sim, {settings.user_title}. O que deseja?"
    return "Sim? O que deseja?"


def run_voice_mode() -> None:
    import threading
    import time

    from core.agent import JarvisAgent
    from voice.audio_player import player
    from voice.listener import listener
    from voice.text_to_speech import speak
    from voice.wake_word import WakeWordDetector

    print(f"\n{settings.jarvis_name.upper()} — modo voz. Ctrl+C para encerrar.\n")
    for warning in settings.validate():
        print(f"[aviso] {warning}")

    _interrupt_words = ("para", "pare", "stop", "chega")

    def _speak_with_interrupt(text: str) -> None:
        print(f"{settings.jarvis_name}: {text}")
        if not settings.voice_enabled:
            return

        def _watch_for_interruption() -> None:
            # Seção 7: enquanto o Jarvis fala, ouve por um pedido de parada.
            while player.is_playing():
                heard = listener.listen_once(phrase_time_limit=2)
                if heard and any(w in heard.lower() for w in _interrupt_words):
                    player.stop()
                    return

        watcher = threading.Thread(target=_watch_for_interruption, daemon=True)
        watcher.start()
        speak(text, blocking=True)

    if not listener.is_ready():
        print(
            "Não consegui acessar um microfone neste computador (verifique se há um "
            "microfone conectado e se pyaudio está instalado). Modo voz indisponível — "
            "use: python main.py --text"
        )
        return

    agent = JarvisAgent(on_reminder_due=_speak_with_interrupt)

    # Evita que o Jarvis reaja de novo à wake word (ou a um eco dela) enquanto
    # já está processando um comando — o detector de wake word continua
    # ouvindo em segundo plano o tempo todo, mesmo durante a saudação e a
    # captura do comando.
    _handling_lock = threading.Lock()

    def _handle_command(prefilled_command: str | None = None) -> None:
        if not _handling_lock.acquire(blocking=False):
            return
        try:
            text = (prefilled_command or "").strip()

            if not text:
                greeting = _wake_greeting()
                print(f"{settings.jarvis_name}: {greeting}")
                if settings.voice_enabled:
                    speak(greeting, blocking=True)

                print("(ouvindo...)")
                text = listener.listen_once(
                    phrase_time_limit=settings.wake_command_phrase_time_limit
                )

            if not text:
                return

            print(f"Você: {text}")
            reply = agent.process(text, response_mode="voice")
            _speak_with_interrupt(reply)
        finally:
            _handling_lock.release()

    _speak_with_interrupt(f"{settings.jarvis_name} online.")

    try:
        if settings.wake_word_enabled:
            print(f"Diga '{settings.wake_word}' para chamar o Jarvis.\n")
            wake_detector = WakeWordDetector(on_wake=_handle_command)
            wake_detector.start()
            while True:
                time.sleep(0.5)
        else:
            print("Modo voz sem wake word: fale seu comando a qualquer momento.\n")
            while True:
                _handle_command()
    except KeyboardInterrupt:
        print("\nEncerrando.")
    finally:
        if "wake_detector" in locals():
            wake_detector.stop()
            wake_detector.join()
        agent.shutdown()


def run_discord_mode() -> None:
    from interface.discord_bot import run_discord_bot

    run_discord_bot()


def run_background_mode() -> None:
    from core.background import BackgroundRuntime

    BackgroundRuntime().run()


def run_doctor() -> int:
    from scripts.doctor import run_doctor as diagnose

    return diagnose()


def run_nexus_mode() -> None:
    """Abre a TUI do NEXUS usando o núcleo, memória e tools deste JARVIS."""
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("O NEXUS precisa de um terminal interativo.")
        return
    from nexus.app import launch

    launch()


def run_gui_mode(minimized: bool = False) -> None:
    # Interface nova (interface_web/), uma janela pywebview mostrando uma
    # página HTML/CSS/JS local — tentada primeiro por conseguir os efeitos
    # de brilho/glow que o CustomTkinter nunca desenhou. Se o pacote
    # `pywebview` não estiver instalado (ou faltar o WebView2 Runtime no
    # Windows, causando falha já dentro de webview.start()), cai sozinho
    # pra interface antiga em CustomTkinter — sem isso, quem ainda não
    # rodou "pip install -r requirements.txt" de novo ficaria sem
    # interface gráfica nenhuma.
    try:
        from interface_web import webview_app

        if webview_app.available():
            try:
                webview_app.run_app(minimized=minimized)
                return
            except Exception:
                logging.getLogger("jarvis.main").exception(
                    "Falha ao abrir a interface pywebview — caindo para a interface CustomTkinter."
                )
    except ImportError:
        pass

    try:
        from interface.app import run_app
    except ImportError:
        print(
            "A interface gráfica é implementada na ETAPA 6 (pasta interface/). "
            "Por enquanto, use: python main.py --text"
        )
        return
    run_app(minimized=minimized)


def main() -> int:
    parser = argparse.ArgumentParser(description="Jarvis — assistente pessoal")
    parser.add_argument("--text", action="store_true", help="Modo texto no terminal")
    parser.add_argument("--voice", action="store_true", help="Modo voz")
    parser.add_argument("--discord", action="store_true", help="Bot do Discord (comando por DM, de fora do PC)")
    parser.add_argument("--debug", action="store_true", help="Ativa logs de debug")
    parser.add_argument("--background", action="store_true", help="Modo invisível/headless para serviço")
    parser.add_argument("--doctor", action="store_true", help="Diagnostica sistema, áudio, Ollama e ROTINA")
    parser.add_argument("--nexus", action="store_true", help="Abre o orquestrador multiagente NEXUS no terminal")
    parser.add_argument(
        "--minimized", action="store_true",
        help="Abre a interface direto minimizada na bandeja (usado pelo início automático com o Windows)",
    )
    args = parser.parse_args()

    if args.debug:
        settings.debug = True
    setup_logging(settings.debug)

    if args.doctor:
        return run_doctor()

    from core.single_instance import AlreadyRunningError, SingleInstanceLock

    instance = SingleInstanceLock(settings.instance_lock_path)
    try:
        instance.acquire()
    except AlreadyRunningError as exc:
        logging.getLogger("jarvis.main").warning("%s", exc)
        return 0

    rotina_manager = None
    try:
        if args.background:
            run_background_mode()
        else:
            from jarvis_rotina import RotinaProcessManager

            rotina_manager = RotinaProcessManager()
            rotina_manager.ensure_running()
            if args.nexus:
                run_nexus_mode()
            elif args.voice:
                run_voice_mode()
            elif args.text:
                run_text_mode()
            elif args.discord:
                run_discord_mode()
            else:
                run_gui_mode(minimized=args.minimized)
    finally:
        if rotina_manager is not None:
            rotina_manager.stop()
        instance.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
