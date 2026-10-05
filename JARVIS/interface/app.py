"""
Interface gráfica do Jarvis — seções 10, 11, 36, 50, 55 do spec.

Usa CustomTkinter (dark theme nativo, 100% Python/Windows, roda de
dentro do VS Code sem precisar de servidor web). A lógica de
negócio é exatamente a mesma do modo texto (core/agent.JarvisAgent)
— a interface só chama agent.process() e reflete o AgentState.

Layout em duas páginas, trocadas pela barra lateral (interface/
components/sidebar.py) em vez de uma tela única fazendo tudo ao mesmo
tempo: "Visão geral" (status do sistema, do agente e das integrações
— antes tudo espremido no topo da janela) e "Conversa" (o chat de
texto/voz, exatamente como antes). Nenhuma função foi perdida na
mudança — só reorganizada.

Paleta: preto / roxo, baseada na logo oficial do Jarvis (estrela roxa
sobre fundo preto — veja `interface/theme.py`, de onde vêm as cores).
"""
from __future__ import annotations

import threading

from config.settings import settings
from core.state import AgentState
from interface import theme

COLOR_BG = theme.BG
COLOR_PANEL = theme.PANEL
COLOR_PURPLE = theme.PURPLE
COLOR_GREEN = theme.PURPLE_LIGHT  # nome mantido por compatibilidade; a logo não tem verde
COLOR_TEXT_DIM = theme.TEXT_DIM
COLOR_ERROR = theme.ERROR

_STATE_COLORS = {
    AgentState.OFFLINE: COLOR_TEXT_DIM,
    AgentState.ONLINE: COLOR_GREEN,
    AgentState.LISTENING: COLOR_PURPLE,
    AgentState.PROCESSING: COLOR_PURPLE,
    AgentState.EXECUTING: COLOR_PURPLE,
    AgentState.SPEAKING: COLOR_GREEN,
    AgentState.ERROR: COLOR_ERROR,
}

_STATE_LABELS = {
    AgentState.OFFLINE: "OFFLINE",
    AgentState.ONLINE: "ONLINE",
    AgentState.LISTENING: "OUVINDO",
    AgentState.PROCESSING: "PROCESSANDO...",
    AgentState.EXECUTING: "EXECUTANDO",
    AgentState.SPEAKING: "FALANDO",
    AgentState.ERROR: "ERRO",
}

_PAGES = (("overview", "🏠", "Visão geral"), ("chat", "💬", "Conversa"))
_PAGE_TITLES = {"overview": "VISÃO GERAL", "chat": "CONVERSA"}


class JarvisApp:
    def __init__(self, root, ctk) -> None:
        from core.agent import JarvisAgent
        from interface.components.activity_panel import ActivityPanel
        from interface.components.automation_panel import AutomationPanel
        from interface.components.chat_panel import ChatPanel
        from interface.components.dashboard_panel import DashboardPanel
        from interface.components.module_status_panel import ModuleStatusPanel
        from interface.components.sidebar import Sidebar
        from interface.components.status_panel import StatusPanel
        from interface.components.voice_animation import VoiceAnimation
        from interface.tray import TrayIcon

        self.root = root
        self.ctk = ctk
        self.agent = JarvisAgent(confirm_callback=self._confirm_dialog, on_reminder_due=self._on_reminder_due)

        # Voz contínua ("jarvis" -> "Sim, Senhor. O que deseja?") ligada
        # direto pela interface — sem precisar de `python main.py --voice`
        # num terminal separado. Ícone na bandeja: fechar a janela só
        # minimiza (o Jarvis continua rodando e ouvindo em segundo plano);
        # sem `pystray` instalado, cai no comportamento antigo (fechar = sair).
        self._wake_detector = None
        self._wake_handling_lock = threading.Lock()
        self._tray = TrayIcon(on_open=self._restore_from_tray, on_quit=self._quit_from_tray)
        if not self._tray.start():
            self._tray = None

        # ----- estrutura geral: barra lateral + área de conteúdo -----
        outer = ctk.CTkFrame(root, fg_color=COLOR_BG)
        outer.pack(fill="both", expand=True)

        self.sidebar = Sidebar(outer, ctk, pages=_PAGES, on_navigate=self._show_page, on_settings=self._open_setup_dialog)
        self.sidebar.frame.pack(side="left", fill="y")

        content = ctk.CTkFrame(outer, fg_color=COLOR_BG)
        content.pack(side="left", fill="both", expand=True)

        topbar = ctk.CTkFrame(content, fg_color="transparent")
        topbar.pack(fill="x", padx=24, pady=(20, 14))
        self._page_title_label = ctk.CTkLabel(
            topbar, text=_PAGE_TITLES["overview"], font=("Segoe UI", 20, "bold"), text_color=theme.TEXT
        )
        self._page_title_label.pack(side="left")
        self.status_panel = StatusPanel(topbar, ctk, _STATE_COLORS, _STATE_LABELS)
        self.status_panel.frame.pack(side="right")

        pages_container = ctk.CTkFrame(content, fg_color="transparent")
        pages_container.pack(fill="both", expand=True, padx=24, pady=(0, 20))
        pages_container.grid_rowconfigure(0, weight=1)
        pages_container.grid_columnconfigure(0, weight=1)

        overview_page = ctk.CTkFrame(pages_container, fg_color="transparent")
        overview_page.grid(row=0, column=0, sticky="nsew")
        chat_page = ctk.CTkFrame(pages_container, fg_color="transparent")
        chat_page.grid(row=0, column=0, sticky="nsew")
        self._pages = {"overview": overview_page, "chat": chat_page}

        # ----- página "Visão geral" -----
        self.dashboard = DashboardPanel(overview_page, ctk)
        self.dashboard.frame.pack(fill="x", pady=(0, 14))

        overview_body = ctk.CTkFrame(overview_page, fg_color="transparent")
        overview_body.pack(fill="both", expand=True)
        overview_body.grid_columnconfigure(0, weight=3)
        overview_body.grid_columnconfigure(1, weight=2)
        overview_body.grid_rowconfigure(0, weight=1)

        overview_left = ctk.CTkFrame(overview_body, fg_color="transparent")
        overview_left.grid(row=0, column=0, sticky="nsew", padx=(0, 14))

        core_card = ctk.CTkFrame(
            overview_left, fg_color=COLOR_PANEL, corner_radius=12, border_width=1, border_color=theme.BORDER_ACCENT
        )
        core_card.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(
            core_card, text="JARVIS CORE", font=("Segoe UI", 12, "bold"), text_color=theme.TEXT_DIM
        ).pack(anchor="w", padx=18, pady=(16, 0))
        self.voice_animation_overview = VoiceAnimation(core_card, ctk, _STATE_COLORS, size=240, base_radius=64)
        self.voice_animation_overview.canvas.pack(pady=16)
        self._overview_state_label = ctk.CTkLabel(
            core_card, text=_STATE_LABELS[AgentState.ONLINE], font=("Segoe UI", 13), text_color=COLOR_TEXT_DIM
        )
        self._overview_state_label.pack(pady=(0, 18))

        from interface import autostart

        self.automation_panel = AutomationPanel(
            overview_left,
            ctk,
            wake_word=settings.wake_word,
            voice_enabled=settings.wake_word_enabled,
            on_toggle_voice=self._on_toggle_continuous_voice,
            autostart_supported=autostart.supported(),
            autostart_enabled=autostart.is_enabled() if autostart.supported() else False,
            on_toggle_autostart=self._on_toggle_autostart,
            tray_active=self._tray is not None,
        )
        self.automation_panel.frame.pack(fill="x")

        overview_right = ctk.CTkFrame(overview_body, fg_color="transparent")
        overview_right.grid(row=0, column=1, sticky="nsew")

        self.module_status_panel = ModuleStatusPanel(overview_right, ctk, get_rows=self._get_module_rows)
        self.module_status_panel.frame.pack(fill="x", pady=(0, 14))

        self.activity_panel = ActivityPanel(overview_right, ctk)
        self.activity_panel.frame.pack(fill="both", expand=True)

        # ----- página "Conversa" -----
        orb_frame = ctk.CTkFrame(chat_page, fg_color=COLOR_PANEL, corner_radius=12, border_width=1, border_color=theme.BORDER)
        orb_frame.pack(fill="x", pady=(0, 10))
        self.voice_animation_chat = VoiceAnimation(orb_frame, ctk, _STATE_COLORS)
        self.voice_animation_chat.canvas.pack(pady=16)
        ctk.CTkLabel(
            orb_frame, text="Como posso ajudar?", font=("Segoe UI", 13), text_color=COLOR_TEXT_DIM
        ).pack(pady=(0, 16))

        self.chat = ChatPanel(chat_page, ctk, on_send=self._handle_send, on_mic=self._handle_mic)
        self.chat.frame.pack(fill="both", expand=True)

        # ----- inicia loops de atualização -----
        self.dashboard.start(root)
        self.activity_panel.start(root)
        self.module_status_panel.start(root)
        self.voice_animation_overview.start(root)
        self.voice_animation_chat.start(root)
        self._poll_agent_state()

        # Os dois frames de página ocupam a mesma célula do grid (ver
        # `_show_page`/pages_container acima) — sem chamar tkraise() aqui, o
        # último a ser criado (Conversa) é quem fica visível por padrão,
        # mesmo com a barra lateral destacando "Visão geral" (bug real visto
        # já no primeiro teste no Windows: a tela mostrava o chat inteiro —
        # orbe pequeno, histórico e caixa de texto — só que com "Visão
        # geral" realçada do lado esquerdo). `_show_page` já faz o
        # tkraise() certo, então é só chamar ele pra abrir na página certa.
        self._show_page("overview")

        self._append_chat(settings.jarvis_name, f"{settings.jarvis_name} online.")
        if settings.voice_enabled:
            threading.Thread(target=self._speak_safely, args=(f"{settings.jarvis_name} online.",), daemon=True).start()

        # Primeira execução sem nenhum provedor de IA configurado -> abre a
        # tela de configuração sozinho, em vez de deixar a pessoa descobrir
        # isso só quando uma resposta vier em modo fallback (parte da
        # preparação do Jarvis pra rodar como .exe, onde ninguém vai abrir
        # o .env num editor de texto).
        if not self.agent.llm.available:
            self.root.after(400, self._open_setup_dialog)

        # Se a voz contínua já estava ligada da última vez (WAKE_WORD_ENABLED
        # salvo no .env), volta a ouvir sozinho ao abrir — importante pra
        # quando o Jarvis abre minimizado com o Windows (--minimized): a
        # pessoa não precisa reabrir a janela só pra reativar isso. Espera
        # alguns segundos antes de checar o microfone — logo depois do
        # Windows ligar (caso do início automático), o driver de áudio às
        # vezes ainda não está pronto, e um cooldown de retry
        # (voice/listener.py) cobre o resto caso ainda assim falhe.
        if settings.wake_word_enabled:
            self.root.after(3000, self._start_wake_detector)

    # ----- navegação entre páginas -----

    def _show_page(self, key: str) -> None:
        self._current_page = key
        self._pages[key].tkraise()
        self.sidebar.set_active(key)
        self._page_title_label.configure(text=_PAGE_TITLES.get(key, key.upper()))

    def _append_chat(self, speaker: str, text: str) -> None:
        """
        Escreve uma linha no chat e, se a pessoa estiver na página "Visão
        geral" quando uma resposta do Jarvis chegar (não o eco do que ela
        mesma disse/digitou), acende um avisinho na aba "Conversa" — sem
        isso, uma resposta chegando enquanto a pessoa está vendo outra
        página passaria despercebida.
        """
        self.chat.append_line(speaker, text)
        if speaker == settings.jarvis_name and self._current_page != "chat":
            self.sidebar.set_badge("chat", True)

    # ----- "Visão geral": status real dos módulos -----

    def _get_module_rows(self) -> list[tuple[str, str, bool]]:
        # A lógica de verdade mora em interface/status_info.py (compartilhada
        # com a interface nova em pywebview — interface_web/) — aqui só
        # converte pro formato de tupla que o ModuleStatusPanel (CustomTkinter)
        # já esperava, pra não precisar mexer nele.
        from interface.status_info import get_module_rows

        return [(row["label"], row["detail"], row["ok"]) for row in get_module_rows(self.agent)]

    # ----- ponte com o agente -----

    def _handle_send(self, text: str) -> None:
        self._append_chat("Você", text)

        def worker() -> None:
            reply = self.agent.process(text)
            self.root.after(0, lambda: self._on_reply(reply))

        threading.Thread(target=worker, daemon=True).start()

    def _on_reply(self, reply: str) -> None:
        self._append_chat(settings.jarvis_name, reply)
        if settings.voice_enabled:
            threading.Thread(target=self._speak_safely, args=(reply,), daemon=True).start()

    def _handle_mic(self) -> None:
        def worker() -> None:
            outcome = None
            try:
                from voice.listener import listener

                if not listener.is_ready():
                    self.root.after(
                        0, lambda: self._append_chat(
                            settings.jarvis_name, "Não consegui acessar um microfone neste computador."
                        )
                    )
                    return
                outcome = listener.listen_once_detailed(phrase_time_limit=10)
            except Exception as exc:
                self.root.after(0, lambda: self._append_chat(settings.jarvis_name, f"Erro no microfone: {exc}"))
                return
            if outcome.text:
                self.root.after(0, lambda: self._handle_send(outcome.text))
                return
            # Antes, qualquer falha aqui ficava muda (sem fala detectada, fala
            # não entendida, erro de captura) — a pessoa falava e nada
            # acontecia, parecendo que o microfone "não reconhecia" nada.
            from voice.listener import feedback_message

            message = feedback_message(outcome)
            if message:
                self.root.after(0, lambda: self._append_chat(settings.jarvis_name, message))

        threading.Thread(target=worker, daemon=True).start()

    # ----- voz contínua ("jarvis" -> "Sim, Senhor. O que deseja?") -----

    def _on_toggle_continuous_voice(self) -> None:
        enabled = self.automation_panel.voice_var.get()
        from config.settings import save_env_values

        try:
            save_env_values({"WAKE_WORD_ENABLED": "true" if enabled else "false"})
        except OSError:
            pass  # não é crítico — o toggle continua valendo só nesta sessão
        settings.wake_word_enabled = enabled

        if enabled:
            self._start_wake_detector()
        else:
            self._stop_wake_detector()

    def _start_wake_detector(self) -> None:
        if self._wake_detector is not None:
            return
        from voice.listener import listener

        if not listener.is_ready():
            self._append_chat(
                settings.jarvis_name,
                "Não consegui acessar um microfone agora — voz contínua indisponível. Se o microfone "
                "estiver conectado normalmente, pode ter sido só uma falha passageira (ex.: o Windows "
                "ainda estava inicializando o áudio); espere alguns segundos e tente ligar o interruptor de novo.",
            )
            self.automation_panel.voice_var.set(False)
            settings.wake_word_enabled = False
            return

        from voice.wake_word import WakeWordDetector

        self._wake_detector = WakeWordDetector(on_wake=self._on_wake_triggered)
        self._wake_detector.start()
        self._append_chat(
            settings.jarvis_name, f'Voz contínua ativada — diga "{settings.wake_word}" pra me chamar a qualquer momento.'
        )

    def _stop_wake_detector(self) -> None:
        if self._wake_detector is not None:
            self._wake_detector.stop()
            self._wake_detector = None
        self._append_chat(settings.jarvis_name, "Voz contínua desativada.")

    def _on_wake_triggered(self, prefilled_command: str | None = None) -> None:
        # Chamado sincronamente pela thread de detecção. Quando o fallback por
        # STT ouve "Jarvis, <comando>", o trecho depois da wake word já chega
        # em prefilled_command e não precisa ser capturado uma segunda vez.
        if not self._wake_handling_lock.acquire(blocking=False):
            return

        try:
            from main import _wake_greeting
            from voice.listener import listener

            text = (prefilled_command or "").strip()

            if not text:
                greeting = _wake_greeting()
                self.root.after(
                    0,
                    lambda: self._append_chat(settings.jarvis_name, greeting),
                )
                if settings.voice_enabled:
                    self._speak_safely(greeting)

                if not listener.is_ready():
                    return
                outcome = listener.listen_once_detailed(
                    phrase_time_limit=settings.wake_command_phrase_time_limit
                )
                if not outcome.text:
                    from voice.listener import feedback_message

                    message = feedback_message(outcome)
                    if message:
                        self.root.after(
                            0,
                            lambda: self._append_chat(
                                settings.jarvis_name,
                                message,
                            ),
                        )
                    return
                text = outcome.text

            self.root.after(0, lambda: self._append_chat("Você", text))
            reply = self.agent.process(text)
            self.root.after(0, lambda: self._on_reply(reply))
        finally:
            self._wake_handling_lock.release()

    # ----- início automático com o Windows -----

    def _on_toggle_autostart(self) -> None:
        from interface import autostart

        enabled = self.automation_panel.autostart_var.get()
        try:
            autostart.set_enabled(enabled)
        except Exception as exc:
            self.automation_panel.autostart_var.set(not enabled)
            self._append_chat(settings.jarvis_name, f"Não consegui alterar o início automático: {exc}")
            return

        msg = (
            "Pronto — vou abrir sozinho (minimizado na bandeja) toda vez que você ligar o Windows."
            if enabled
            else "Início automático com o Windows desligado."
        )
        self._append_chat(settings.jarvis_name, msg)

    # ----- ícone na bandeja -----

    def _restore_from_tray(self) -> None:
        self.root.after(0, self._do_restore_from_tray)

    def _do_restore_from_tray(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _quit_from_tray(self) -> None:
        self.root.after(0, self._shutdown)

    def _speak_safely(self, text: str) -> None:
        try:
            from voice.text_to_speech import speak

            speak(text)
        except Exception:
            pass

    def _on_reminder_due(self, message: str) -> None:
        self.root.after(0, lambda: self._append_chat(settings.jarvis_name, message))
        if settings.voice_enabled:
            threading.Thread(target=self._speak_safely, args=(message,), daemon=True).start()

    def _confirm_dialog(self, message: str) -> bool:
        """
        Confirmação de ações MEDIUM/HIGH/CRITICAL (core/permissions.py) via
        caixa de diálogo modal — chamada a partir de uma thread de trabalho,
        então usa uma variável compartilhada + wait_variable para bloquear
        aquela thread até o usuário responder, sem travar a UI principal.
        """
        result: dict = {"value": False}
        done = threading.Event()

        def _show() -> None:
            dialog = self.ctk.CTkToplevel(self.root)
            dialog.title("Confirmação necessária")
            dialog.geometry("420x160")
            dialog.configure(fg_color=COLOR_PANEL)
            dialog.attributes("-topmost", True)

            self.ctk.CTkLabel(
                dialog, text=message, font=("Segoe UI", 13), text_color=theme.TEXT, wraplength=380, justify="left"
            ).pack(padx=20, pady=(20, 16))

            btn_row = self.ctk.CTkFrame(dialog, fg_color="transparent")
            btn_row.pack(pady=8)

            def _answer(value: bool) -> None:
                result["value"] = value
                done.set()
                dialog.destroy()

            self.ctk.CTkButton(
                btn_row, text="Cancelar", fg_color=theme.SURFACE, hover_color=theme.SURFACE_HOVER, command=lambda: _answer(False)
            ).pack(side="left", padx=8)
            self.ctk.CTkButton(
                btn_row, text="Confirmar", fg_color=COLOR_PURPLE, hover_color=theme.PURPLE_HOVER, command=lambda: _answer(True)
            ).pack(side="left", padx=8)

            dialog.protocol("WM_DELETE_WINDOW", lambda: _answer(False))

        self.root.after(0, _show)
        done.wait(timeout=120)  # nunca trava para sempre; some após 2 min sem resposta = recusado
        return result["value"]

    def _open_setup_dialog(self) -> None:
        from interface.components.setup_dialog import SetupDialog

        SetupDialog(self.root, self.ctk, on_saved=self._reload_agent)

    def _reload_agent(self) -> None:
        """
        Chamado depois que a tela de configuração salva um provedor/chave
        novo no .env — relê as configurações e recria o agente (que é
        onde o LLMProvider é escolhido), sem precisar fechar e reabrir o
        Jarvis inteiro.
        """
        from config.settings import reload_settings
        from core.agent import JarvisAgent

        reload_settings()
        self.agent = JarvisAgent(confirm_callback=self._confirm_dialog, on_reminder_due=self._on_reminder_due)
        status = "conectado" if self.agent.llm.available else "ainda sem chave configurada"
        self._append_chat(settings.jarvis_name, f"Configuração recarregada — provedor de IA {status}.")

    def _poll_agent_state(self) -> None:
        state = self.agent.state
        self.status_panel.set_state(state)
        self.voice_animation_overview.set_state(state)
        self.voice_animation_chat.set_state(state)
        self._overview_state_label.configure(text=_STATE_LABELS.get(state, state.value))
        self.root.after(200, self._poll_agent_state)

    def on_close(self) -> None:
        # Com ícone na bandeja disponível, fechar a janela (botão X) só
        # minimiza — igual WhatsApp/Discord/Spotify — pra não derrubar a voz
        # contínua nem exigir reabrir o Jarvis toda hora. Sem bandeja
        # disponível (pystray não instalado), mantém o comportamento antigo:
        # fechar a janela encerra o programa de verdade.
        if self._tray is not None:
            self.root.withdraw()
            return
        self._shutdown()

    def _shutdown(self) -> None:
        if self._wake_detector is not None:
            self._wake_detector.stop()
            self._wake_detector = None
        if self._tray is not None:
            self._tray.stop()
            self._tray = None
        self.agent.shutdown()
        self.root.destroy()


def run_app(minimized: bool = False) -> None:
    try:
        import customtkinter as ctk
    except ImportError:
        print(
            "A interface gráfica requer o pacote customtkinter (pip install customtkinter). "
            "Use: python main.py --text"
        )
        return

    ctk.set_appearance_mode("dark")

    root = ctk.CTk()
    root.title(settings.jarvis_name.upper())
    root.geometry("1220x760")
    root.minsize(960, 620)
    root.configure(fg_color=COLOR_BG)

    app = JarvisApp(root, ctk)
    root.protocol("WM_DELETE_WINDOW", app.on_close)

    if minimized:
        if app._tray is not None:
            root.withdraw()
        else:
            print(
                "Ícone da bandeja indisponível (pip install pystray) — abrindo a janela "
                "normalmente em vez de minimizada."
            )

    root.mainloop()
