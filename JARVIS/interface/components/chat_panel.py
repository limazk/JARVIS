"""
Chat: histórico + campo de texto + botão de microfone (seção 9 do spec).
"""
from __future__ import annotations

from typing import Callable, Optional

from interface import theme


class ChatPanel:
    def __init__(
        self,
        parent,
        ctk,
        on_send: Callable[[str], None],
        on_mic: Optional[Callable[[], None]] = None,
    ) -> None:
        self._on_send = on_send
        self.frame = ctk.CTkFrame(parent, fg_color=theme.PANEL, corner_radius=12)

        self.history = ctk.CTkTextbox(
            self.frame, fg_color=theme.SURFACE, text_color=theme.TEXT, font=("Segoe UI", 13), wrap="word"
        )
        self.history.pack(fill="both", expand=True, padx=14, pady=(14, 8))
        self.history.configure(state="disabled")

        input_row = ctk.CTkFrame(self.frame, fg_color="transparent")
        input_row.pack(fill="x", padx=14, pady=(0, 14))

        self.entry = ctk.CTkEntry(
            input_row,
            placeholder_text="Digite uma mensagem...",
            fg_color=theme.SURFACE,
            border_color=theme.PURPLE,
            text_color=theme.TEXT,
            height=40,
        )
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entry.bind("<Return>", lambda _event: self._send())

        send_btn = ctk.CTkButton(
            input_row, text="Enviar", width=84, height=40,
            fg_color=theme.PURPLE, hover_color=theme.PURPLE_HOVER, command=self._send,
        )
        send_btn.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            input_row, text="🎙", width=44, height=40,
            fg_color=theme.SURFACE, hover_color=theme.SURFACE_HOVER,
            border_width=1, border_color=theme.PURPLE_LIGHT,
            command=on_mic or (lambda: None),
        ).pack(side="left")

    def _send(self) -> None:
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        self._on_send(text)

    def append_line(self, speaker: str, text: str) -> None:
        self.history.configure(state="normal")
        self.history.insert("end", f"{speaker}: {text}\n\n")
        self.history.configure(state="disabled")
        self.history.see("end")
