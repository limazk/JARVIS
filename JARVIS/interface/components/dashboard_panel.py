"""
Dashboard de sistema — CPU/RAM/disco/hora (seções 10 e 55 do spec).

Atualiza periodicamente via root.after() (sem thread própria —
psutil.cpu_percent(interval=None) é rápido o suficiente para não
travar a UI). GPU não é exibida por padrão neste protótipo: a RX 7600
(AMD) não expõe uso de GPU por uma lib multiplataforma simples como o
psutil faz pra CPU/RAM — mostrar um número "GPU: --" sempre parado
seria pior que não mostrar nada. Fica documentada a possibilidade de
estender com pyadl/pyamdgpuinfo (AMD) ou GPUtil/pynvml (NVIDIA) quando
o hardware específico for conhecido.

Cada métrica é um card com borda fina (visual "Visão geral" novo) e
uma barrinha de progresso proporcional ao valor — só cosmético, não
depende de nada além do psutil que este componente já usava.
"""
from __future__ import annotations

import platform
from datetime import datetime

from interface import theme


class DashboardPanel:
    REFRESH_MS = 2000

    # (chave, título, mostra barra de progresso?)
    _METRICS = (("cpu", "CPU", True), ("ram", "RAM", True), ("disco", "DISCO", True), ("hora", "HORA", False))

    def __init__(self, parent, ctk) -> None:
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")

        self._values: dict = {}
        self._bars: dict = {}
        for key, title, has_bar in self._METRICS:
            cell = ctk.CTkFrame(
                self.frame, fg_color=theme.PANEL, corner_radius=12, border_width=1, border_color=theme.BORDER
            )
            cell.pack(side="left", expand=True, fill="both", padx=(0, 10))
            inner = ctk.CTkFrame(cell, fg_color="transparent")
            inner.pack(fill="both", expand=True, padx=16, pady=12)

            ctk.CTkLabel(inner, text=title, font=("Segoe UI", 11), text_color=theme.TEXT_DIM).pack(anchor="w")
            value_label = ctk.CTkLabel(inner, text="--", font=("Segoe UI", 22, "bold"), text_color=theme.TEXT)
            value_label.pack(anchor="w", pady=(2, 0))
            self._values[key] = value_label

            if has_bar:
                bar = ctk.CTkProgressBar(
                    inner, height=6, fg_color=theme.SURFACE, progress_color=theme.PURPLE, corner_radius=3
                )
                bar.set(0)
                bar.pack(fill="x", pady=(10, 0))
                self._bars[key] = bar

        self._root = None

    def start(self, root) -> None:
        self._root = root
        self._tick()

    def _set(self, key: str, percent: float) -> None:
        self._values[key].configure(text=f"{percent:.0f}%")
        bar = self._bars.get(key)
        if bar is not None:
            bar.set(max(0.0, min(1.0, percent / 100)))

    def _tick(self) -> None:
        try:
            import psutil

            self._set("cpu", psutil.cpu_percent(interval=None))
            self._set("ram", psutil.virtual_memory().percent)
            disk_path = "C:\\" if platform.system() == "Windows" else "/"
            self._set("disco", psutil.disk_usage(disk_path).percent)
        except Exception:
            pass
        self._values["hora"].configure(text=datetime.now().strftime("%H:%M"))

        if self._root is not None:
            self._root.after(self.REFRESH_MS, self._tick)
