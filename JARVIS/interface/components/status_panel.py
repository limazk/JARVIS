"""
Painel de status — mostra "● ONLINE" e o estado atual do agente
(seções 10 e 36 do spec: OFFLINE/ONLINE/LISTENING/PROCESSING/
EXECUTING/SPEAKING/ERROR).
"""
from __future__ import annotations

from core.state import AgentState
from interface import theme


class StatusPanel:
    def __init__(self, parent, ctk, colors: dict, labels: dict) -> None:
        self._colors = colors
        self._labels = labels

        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.dot = ctk.CTkLabel(self.frame, text="●", font=("Segoe UI", 18), text_color=colors[AgentState.ONLINE])
        self.dot.pack(side="left", padx=(0, 6))
        self.label = ctk.CTkLabel(self.frame, text="ONLINE", font=("Segoe UI", 15, "bold"), text_color=theme.TEXT)
        self.label.pack(side="left")

    def set_state(self, state: AgentState) -> None:
        self.dot.configure(text_color=self._colors.get(state, theme.TEXT_DIM))
        self.label.configure(text=self._labels.get(state, state.value))
