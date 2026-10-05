"""
Animação central — "orbe" que reage ao estado do agente (seção 11 do spec).

Implementação simples em Canvas: cor e "pulso" (raio) mudam conforme
o estado (ONLINE parado, OUVINDO/PROCESSANDO/FALANDO pulsando mais
rápido). Não é um visualizador de áudio real ligado à forma de onda
— isso é polimento visual de roadmap (seção 61: "não sacrifique
funcionalidade por aparência" é a prioridade #1 deste protótipo).
"""
from __future__ import annotations

import math
import tkinter as tk

from core.state import AgentState
from interface import theme

_SPEED_BY_STATE = {
    AgentState.PROCESSING: 6.0,
    AgentState.EXECUTING: 5.0,
    AgentState.SPEAKING: 8.0,
    AgentState.LISTENING: 4.0,
}


class VoiceAnimation:
    SIZE = 220
    BASE_RADIUS = 55

    def __init__(self, parent, ctk, colors: dict, size: int | None = None, base_radius: int | None = None) -> None:
        self._colors = colors
        # `size`/`base_radius` permitem um "orbe" maior na página Visão geral
        # (o card de destaque, papel do "núcleo" na interface) e um menor,
        # mais discreto, acima do chat na página Conversa — mesmo desenho,
        # só a escala muda.
        self.SIZE = size if size is not None else self.SIZE
        self.BASE_RADIUS = base_radius if base_radius is not None else self.BASE_RADIUS
        self.canvas = tk.Canvas(parent, width=self.SIZE, height=self.SIZE, bg=theme.PANEL, highlightthickness=0)
        self._state = AgentState.ONLINE
        self._tick_count = 0
        self._root = None

    def start(self, root) -> None:
        self._root = root
        self._tick()

    def set_state(self, state: AgentState) -> None:
        self._state = state

    def _tick(self) -> None:
        self._tick_count += 1
        self.canvas.delete("all")

        cx = cy = self.SIZE / 2
        speed = _SPEED_BY_STATE.get(self._state, 1.5)
        pulse = math.sin(self._tick_count / 10 * speed) * 8
        color = self._colors.get(self._state, theme.PURPLE)

        # Dois anéis externos discretos + núcleo preenchido que pulsa.
        for extra in (24, 12):
            r = self.BASE_RADIUS + extra
            self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline=color, width=1)

        radius = self.BASE_RADIUS + pulse
        self.canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, fill=color, outline="")

        if self._root is not None:
            self._root.after(60, self._tick)
