"""
Painel "AUTOMAÇÃO" — os interruptores de voz contínua e início
automático com o Windows, antes soltos numa barra no topo da janela
(fora de qualquer aba); agora reunidos num card próprio na página
"Visão geral". A lógica de cada toggle continua inteira em
interface/app.py — este componente só monta os widgets e expõe as
BooleanVar pra quem criou ele poder ler/ajustar (ex.: desligar o
interruptor sozinho se o microfone não estiver disponível).
"""
from __future__ import annotations

from typing import Callable, Optional

from interface import theme


class AutomationPanel:
    def __init__(
        self,
        parent,
        ctk,
        *,
        wake_word: str,
        voice_enabled: bool,
        on_toggle_voice: Callable[[], None],
        autostart_supported: bool,
        autostart_enabled: bool,
        on_toggle_autostart: Callable[[], None],
        tray_active: bool,
    ) -> None:
        self.frame = ctk.CTkFrame(
            parent, fg_color=theme.PANEL, corner_radius=12, border_width=1, border_color=theme.BORDER
        )
        ctk.CTkLabel(
            self.frame, text="AUTOMAÇÃO", font=("Segoe UI", 12, "bold"), text_color=theme.TEXT_DIM
        ).pack(anchor="w", padx=16, pady=(14, 10))

        body = ctk.CTkFrame(self.frame, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        self.voice_var = ctk.BooleanVar(value=voice_enabled)
        ctk.CTkSwitch(
            body,
            text=f'Voz contínua ("{wake_word}")',
            variable=self.voice_var,
            onvalue=True,
            offvalue=False,
            progress_color=theme.PURPLE,
            command=on_toggle_voice,
        ).pack(anchor="w", pady=6)

        self.autostart_var: Optional[object] = None
        if autostart_supported:
            self.autostart_var = ctk.BooleanVar(value=autostart_enabled)
            ctk.CTkSwitch(
                body,
                text="Iniciar com o Windows",
                variable=self.autostart_var,
                onvalue=True,
                offvalue=False,
                progress_color=theme.PURPLE,
                command=on_toggle_autostart,
            ).pack(anchor="w", pady=6)

        tray_text = (
            "Ícone na bandeja: ativo (fechar a janela só minimiza)"
            if tray_active
            else "Ícone na bandeja: indisponível (pip install pystray)"
        )
        ctk.CTkLabel(body, text=tray_text, font=("Segoe UI", 11), text_color=theme.TEXT_DIM).pack(
            anchor="w", pady=(10, 0)
        )
