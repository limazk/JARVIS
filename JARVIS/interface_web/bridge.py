"""
WebBridge — ponte Python <-> JavaScript da interface pywebview.

Um objeto desta classe é passado como `js_api` para
`webview.create_window(...)` (ver `interface_web/webview_app.py`):
todo método público vira `pywebview.api.<nome>(...)` no JavaScript,
devolvendo uma Promise. O front-end (interface_web/web/app.js) usa um
modelo de POLLING em vez de "push" (chamar `get_snapshot()`/
`get_messages()` a cada ~1s) — mais simples e robusto que depender de
`window.evaluate_js()` a partir de threads de trabalho em segundo
plano, e este é um app pessoal local, não um serviço de alto tráfego,
então o custo de reconsultar o estado inteiro a cada segundo é
irrelevante.

Nenhum destes métodos importa `webview` ou faz qualquer coisa que só
funcione dentro de uma janela pywebview de verdade — a única exceção é
o controle da PRÓPRIA janela (minimizar/restaurar/fechar), que usa o
objeto `window` (guardado em `self.window`, atribuído de fora por
`webview_app.py` depois de criar a janela) só através dos métodos
`.hide()`/`.restore()`/`.show()`/`.destroy()` documentados pela API do
pywebview — nunca importando o pacote em si. Isso mantém toda a lógica
de negócio (chat, confirmações de permissão, toggles de automação,
configuração de IA) testável neste projeto sem o pacote `pywebview`
instalado (ele não está disponível no ambiente onde este código foi
escrito — ver o comentário em requirements.txt), do mesmo jeito que
`interface/app.py` sempre foi testado indiretamente, sem testar a
camada de CustomTkinter em si.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from config.settings import settings

logger = logging.getLogger("jarvis.interface_web.bridge")

# Quantas mensagens de chat manter em memória (não é o histórico de
# longo prazo — isso já é feito por core/context.py e memory/ — só o
# que a página de Conversa consegue mostrar de uma vez).
_MAX_MESSAGES = 200

# Uma confirmação sem resposta em 2 minutos é tratada como recusada —
# mesmo limite e mesmo motivo do diálogo modal do CustomTkinter
# (interface/app.py::_confirm_dialog): nunca trava a thread de trabalho
# pra sempre só porque a pessoa não está olhando pra tela.
_CONFIRMATION_TIMEOUT_S = 120


class WebBridge:
    def __init__(self) -> None:
        from core.agent import JarvisAgent

        self.window = None  # atribuído por webview_app.py depois de create_window()
        self._started_at = time.monotonic()

        self._lock = threading.Lock()
        self._messages: list[dict] = []
        self._next_message_id = 1
        self._current_page = "overview"
        self._chat_unread = False

        self._pending_confirmation: Optional[dict] = None
        self._confirmation_entries: dict[int, dict] = {}
        self._next_confirmation_id = 1

        self._wake_detector = None
        self._wake_handling_lock = threading.Lock()
        self._tray = None

        self.agent = JarvisAgent(confirm_callback=self._confirm_dialog, on_reminder_due=self._on_reminder_due)

        self._append_message(settings.jarvis_name, f"{settings.jarvis_name} online.")
        if settings.voice_enabled:
            threading.Thread(
                target=self._speak_safely, args=(f"{settings.jarvis_name} online.",), daemon=True
            ).start()

        # Mesmo motivo do atraso em interface/app.py: logo depois do
        # Windows ligar (início automático), o driver de áudio às vezes
        # ainda não está pronto — dar um tempinho evita um falso
        # "microfone indisponível" na primeira tentativa.
        if settings.wake_word_enabled:
            threading.Timer(3.0, self._start_wake_detector).start()

    # ----- ciclo de vida / bandeja -----

    def start_tray(self) -> None:
        """Chamado por webview_app.py depois que a janela existe."""
        from interface.tray import TrayIcon

        self._tray = TrayIcon(on_open=self._restore_from_tray, on_quit=self._quit_from_tray)
        if not self._tray.start():
            self._tray = None

    def attach_window(self, window) -> None:
        self.window = window

    def _restore_from_tray(self) -> None:
        if self.window is None:
            return
        try:
            self.window.restore()
            self.window.show()
        except Exception:  # noqa: BLE001 — nunca derruba a thread do ícone da bandeja
            logger.exception("Falha ao restaurar a janela a partir da bandeja.")

    def _quit_from_tray(self) -> None:
        self.shutdown_and_close()

    def on_window_closing(self) -> bool:
        """
        Chamado pelo handler do evento `closing` do pywebview (ver
        webview_app.py). Documentado a partir da API oficial do
        pywebview — devolver False do handler cancela o fechamento da
        janela; não foi possível testar isso ao vivo neste ambiente
        (sem pywebview instalado — ver requirements.txt), então vale
        confirmar esse comportamento na primeira execução real.

        Com bandeja disponível, replica o comportamento do X do
        CustomTkinter: só esconde a janela (o Jarvis continua rodando/
        ouvindo em segundo plano). Sem bandeja, deixa fechar de verdade.
        """
        if self._tray is not None:
            if self.window is not None:
                try:
                    self.window.hide()
                except Exception:  # noqa: BLE001
                    logger.exception("Falha ao esconder a janela ao fechar.")
            return False
        self.shutdown()
        return True

    def shutdown(self) -> None:
        if self._wake_detector is not None:
            self._wake_detector.stop()
            self._wake_detector = None
        if self._tray is not None:
            self._tray.stop()
            self._tray = None
        self.agent.shutdown()

    def shutdown_and_close(self) -> None:
        self.shutdown()
        if self.window is not None:
            try:
                self.window.destroy()
            except Exception:  # noqa: BLE001
                logger.exception("Falha ao fechar a janela.")

    # ----- estado consultado pelo front-end (polling) -----

    def set_page(self, key: str) -> dict:
        """
        Chamado pelo JS ao trocar de página na barra lateral — mesma
        lógica de "aviso na aba Conversa" do CustomTkinter
        (interface/app.py::_append_chat): entrar na página "Conversa"
        limpa o avisinho de mensagem não lida.
        """
        with self._lock:
            self._current_page = key
            if key == "chat":
                self._chat_unread = False
        return {"ok": True}

    def get_snapshot(self) -> dict:
        from interface import autostart
        from interface.status_info import get_activity_rows, get_module_rows, get_stats, get_top_processes

        with self._lock:
            pending = dict(self._pending_confirmation) if self._pending_confirmation else None
            chat_unread = self._chat_unread

        return {
            "state": self.agent.state.value,
            "stats": get_stats(),
            "module_rows": get_module_rows(self.agent),
            "process_rows": get_top_processes(limit=6),
            "activity_rows": get_activity_rows(limit=30),
            "chat_unread": chat_unread,
            "pending_confirmation": pending,
            "voice_enabled": settings.wake_word_enabled,
            "autostart_supported": autostart.supported(),
            "autostart_enabled": autostart.is_enabled() if autostart.supported() else False,
            "tray_active": self._tray is not None,
            "wake_word": settings.wake_word,
            "jarvis_name": settings.jarvis_name,
            "llm_available": self.agent.llm.available,
            # Métricas reais e honestas pro card "JARVIS CORE" (nada de
            # fabricar um "99.98% uptime" — o Jarvis não mede isso hoje):
            # tempo desde que esta janela foi aberta e quantas mensagens
            # já passaram pelo chat nesta sessão.
            "uptime_seconds": time.monotonic() - self._started_at,
            "message_count": self._next_message_id - 1,
            # Especialista (core/specialists.py) que respondeu a última
            # mensagem que passou pelo LLM, ou None em modo geral — ver
            # Router.last_specialist. Nenhuma das duas interfaces é
            # obrigada a mostrar isso hoje; existe pra estar disponível.
            "active_specialist": self.agent.router.last_specialist,
        }

    def get_messages(self, since_id: int = 0) -> list[dict]:
        with self._lock:
            return [m for m in self._messages if m["id"] > since_id]

    # ----- chat -----

    def _append_message(self, speaker: str, text: str) -> dict:
        with self._lock:
            msg = {"id": self._next_message_id, "speaker": speaker, "text": text}
            self._next_message_id += 1
            self._messages.append(msg)
            if len(self._messages) > _MAX_MESSAGES:
                self._messages = self._messages[-_MAX_MESSAGES:]
            if speaker == settings.jarvis_name and self._current_page != "chat":
                self._chat_unread = True
        return msg

    def send_text(self, text: str) -> dict:
        text = (text or "").strip()
        if not text:
            return {"ok": False}
        self._append_message("Você", text)

        def worker() -> None:
            reply = self.agent.process(text)
            self._append_message(settings.jarvis_name, reply)
            if settings.voice_enabled:
                self._speak_safely(reply)

        threading.Thread(target=worker, daemon=True).start()
        return {"ok": True}

    def request_mic(self) -> dict:
        def worker() -> None:
            try:
                from voice.listener import feedback_message, listener

                if not listener.is_ready():
                    self._append_message(settings.jarvis_name, "Não consegui acessar um microfone neste computador.")
                    return
                outcome = listener.listen_once_detailed(phrase_time_limit=10)
            except Exception as exc:  # noqa: BLE001
                self._append_message(settings.jarvis_name, f"Erro no microfone: {exc}")
                return
            if outcome.text:
                self.send_text(outcome.text)
                return
            # Antes, qualquer falha aqui (sem fala detectada, fala não
            # entendida, erro de captura) ficava muda — a pessoa falava e
            # nada acontecia na tela, parecendo que o microfone "não
            # reconhecia" nada. Agora cada motivo tem um aviso específico.
            message = feedback_message(outcome)
            if message:
                self._append_message(settings.jarvis_name, message)

        threading.Thread(target=worker, daemon=True).start()
        return {"ok": True}

    def _speak_safely(self, text: str) -> None:
        try:
            from voice.text_to_speech import speak

            speak(text)
        except Exception:  # noqa: BLE001
            logger.exception("Falha ao falar a resposta.")

    def _on_reminder_due(self, message: str) -> None:
        self._append_message(settings.jarvis_name, message)
        if settings.voice_enabled:
            threading.Thread(target=self._speak_safely, args=(message,), daemon=True).start()

    # ----- voz contínua ("jarvis" -> "Sim, Senhor. O que deseja?") -----

    def toggle_voice(self, enabled: bool) -> dict:
        from config.settings import save_env_values

        try:
            save_env_values({"WAKE_WORD_ENABLED": "true" if enabled else "false"})
        except OSError:
            pass  # não é crítico — o toggle continua valendo só nesta sessão
        settings.wake_word_enabled = bool(enabled)

        if enabled:
            ok = self._start_wake_detector()
        else:
            self._stop_wake_detector()
            ok = True
        return {"ok": ok, "enabled": settings.wake_word_enabled}

    def _start_wake_detector(self) -> bool:
        if self._wake_detector is not None:
            return True
        from voice.listener import listener

        if not listener.is_ready():
            self._append_message(
                settings.jarvis_name,
                "Não consegui acessar um microfone agora — voz contínua indisponível. Se o microfone "
                "estiver conectado normalmente, pode ter sido só uma falha passageira (ex.: o Windows "
                "ainda estava inicializando o áudio); espere alguns segundos e tente ligar de novo.",
            )
            settings.wake_word_enabled = False
            return False

        from voice.wake_word import WakeWordDetector

        self._wake_detector = WakeWordDetector(on_wake=self._on_wake_triggered)
        self._wake_detector.start()
        self._append_message(
            settings.jarvis_name, f'Voz contínua ativada — diga "{settings.wake_word}" pra me chamar a qualquer momento.'
        )
        return True

    def _stop_wake_detector(self) -> None:
        if self._wake_detector is not None:
            self._wake_detector.stop()
            self._wake_detector = None
        self._append_message(settings.jarvis_name, "Voz contínua desativada.")

    def _on_wake_triggered(self) -> None:
        # Ver o comentário equivalente em interface/app.py::_on_wake_triggered
        # — o lock não-bloqueante evita duas capturas de microfone
        # concorrentes brigando pelo mesmo listener compartilhado.
        if not self._wake_handling_lock.acquire(blocking=False):
            return

        try:
            from main import _wake_greeting
            from voice.listener import feedback_message, listener

            greeting = _wake_greeting()
            self._append_message(settings.jarvis_name, greeting)
            if settings.voice_enabled:
                self._speak_safely(greeting)

            if not listener.is_ready():
                return
            outcome = listener.listen_once_detailed(phrase_time_limit=10)
            if not outcome.text:
                message = feedback_message(outcome)
                if message:
                    self._append_message(settings.jarvis_name, message)
                return
            self._append_message("Você", outcome.text)
            reply = self.agent.process(outcome.text)
            self._append_message(settings.jarvis_name, reply)
            if settings.voice_enabled:
                self._speak_safely(reply)
        finally:
            self._wake_handling_lock.release()

    # ----- início automático com o Windows -----

    def toggle_autostart(self, enabled: bool) -> dict:
        from interface import autostart

        try:
            autostart.set_enabled(bool(enabled))
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "error": str(exc),
                "enabled": autostart.is_enabled() if autostart.supported() else False,
            }

        msg = (
            "Pronto — vou abrir sozinho (minimizado na bandeja) toda vez que você ligar o Windows."
            if enabled
            else "Início automático com o Windows desligado."
        )
        self._append_message(settings.jarvis_name, msg)
        return {"ok": True, "enabled": bool(enabled)}

    # ----- confirmação de ações MEDIUM/HIGH/CRITICAL -----

    def _confirm_dialog(self, message: str) -> bool:
        """
        Chamado por core/permissions.py de dentro da thread de trabalho
        que está processando um comando (nunca da "thread principal",
        que aqui nem existe da mesma forma que no Tkinter — pywebview
        roda sua própria janela em segundo plano). Bloqueia essa thread
        até `answer_confirmation` ser chamado pelo JS (ou 2 minutos
        passarem sem resposta, tratado como recusa).
        """
        event = threading.Event()
        with self._lock:
            confirmation_id = self._next_confirmation_id
            self._next_confirmation_id += 1
            self._confirmation_entries[confirmation_id] = {"event": event, "result": False}
            self._pending_confirmation = {"id": confirmation_id, "message": message}

        event.wait(timeout=_CONFIRMATION_TIMEOUT_S)

        with self._lock:
            entry = self._confirmation_entries.pop(confirmation_id, None)
            if self._pending_confirmation and self._pending_confirmation.get("id") == confirmation_id:
                self._pending_confirmation = None

        return bool(entry["result"]) if entry else False

    def answer_confirmation(self, confirmation_id: int, value: bool) -> dict:
        with self._lock:
            entry = self._confirmation_entries.get(confirmation_id)
            if entry is None:
                return {"ok": False}
            entry["result"] = bool(value)
            if self._pending_confirmation and self._pending_confirmation.get("id") == confirmation_id:
                self._pending_confirmation = None
        entry["event"].set()
        return {"ok": True}

    # ----- tela "Configurar IA" -----

    def get_llm_config(self) -> dict:
        from interface.components.setup_dialog import _PROVIDERS

        providers = [
            {"value": value, "label": label, "needs_key": key_name is not None, "key_url": url}
            for value, label, key_name, url in _PROVIDERS
        ]
        valid_values = [p["value"] for p in providers]
        current = settings.llm_provider if settings.llm_provider in valid_values else "gemini"
        return {"providers": providers, "current_provider": current, "llm_available": self.agent.llm.available}

    def save_llm_config(self, provider: str, api_key: str) -> dict:
        from config.settings import reload_settings, save_env_values
        from core.agent import JarvisAgent
        from interface.components.setup_dialog import _PROVIDERS

        entry = next((p for p in _PROVIDERS if p[0] == provider), None)
        if entry is None:
            return {"ok": False, "error": "Provedor desconhecido."}
        _value, _label, key_name, _url = entry

        to_save = {"LLM_PROVIDER": provider}
        if key_name is not None:
            key = (api_key or "").strip()
            if not key:
                return {"ok": False, "error": "Cole a chave antes de salvar."}
            to_save[key_name] = key

        try:
            save_env_values(to_save)
        except OSError as exc:
            return {"ok": False, "error": f"Não consegui salvar: {exc}"}

        reload_settings()
        self.agent = JarvisAgent(confirm_callback=self._confirm_dialog, on_reminder_due=self._on_reminder_due)
        status = "conectado" if self.agent.llm.available else "ainda sem chave configurada"
        self._append_message(settings.jarvis_name, f"Configuração recarregada — provedor de IA {status}.")
        return {"ok": True, "llm_available": self.agent.llm.available}
