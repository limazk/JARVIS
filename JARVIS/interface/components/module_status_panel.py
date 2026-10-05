"""
Painel "MÓDULOS" — lista, com um pontinho colorido, quais partes do
Jarvis estão realmente configuradas/prontas agora (IA, voz, memória,
integrações). Cada linha vem de `get_rows()`, uma função fornecida por
quem cria o painel (normalmente interface/app.py) que sabe consultar o
estado real (config/settings.py, o agente, o microfone) — este
componente só desenha o que recebe, nunca inventa status.

`get_rows()` deve sempre devolver a mesma lista de módulos, na mesma
ordem, mudando só o texto/cor de cada linha — assim os widgets são
criados uma única vez e cada atualização só troca texto (sem destruir
e recriar nada, o que evitaria um "pisca" visual a cada refresh).
"""
from __future__ import annotations

from typing import Callable, List, Tuple

from interface import theme

# (rótulo do módulo, detalhe, ok?)
Row = Tuple[str, str, bool]


class ModuleStatusPanel:
    REFRESH_MS = 4000

    def __init__(self, parent, ctk, get_rows: Callable[[], List[Row]]) -> None:
        self._get_rows = get_rows
        self._ctk = ctk
        self._root = None
        self._row_widgets: list[tuple] = []  # (dot_label, name_label, detail_label)

        self.frame = ctk.CTkFrame(
            parent, fg_color=theme.PANEL, corner_radius=12, border_width=1, border_color=theme.BORDER
        )
        ctk.CTkLabel(
            self.frame, text="MÓDULOS", font=("Segoe UI", 12, "bold"), text_color=theme.TEXT_DIM
        ).pack(anchor="w", padx=16, pady=(14, 6))

        self._rows_frame = ctk.CTkFrame(self.frame, fg_color="transparent")
        self._rows_frame.pack(fill="both", expand=True, padx=16, pady=(0, 14))

        try:
            initial_rows = get_rows()
        except Exception:
            initial_rows = []
        self._build_rows(initial_rows)

    def _build_rows(self, rows: List[Row]) -> None:
        ctk = self._ctk
        for label, detail, ok in rows:
            row = ctk.CTkFrame(self._rows_frame, fg_color="transparent")
            row.pack(fill="x", pady=4)

            dot = ctk.CTkLabel(row, text="●", font=("Segoe UI", 12), text_color=theme.OK if ok else theme.TEXT_DIM)
            dot.pack(side="left", padx=(0, 8))

            text_col = ctk.CTkFrame(row, fg_color="transparent")
            text_col.pack(side="left", fill="x", expand=True)
            name_label = ctk.CTkLabel(
                text_col, text=label, font=("Segoe UI", 13), text_color=theme.TEXT, anchor="w"
            )
            name_label.pack(anchor="w")
            detail_label = ctk.CTkLabel(
                text_col, text=detail, font=("Segoe UI", 11), text_color=theme.TEXT_DIM, anchor="w"
            )
            detail_label.pack(anchor="w")

            self._row_widgets.append((dot, name_label, detail_label))

    def start(self, root) -> None:
        self._root = root
        self._tick()

    def _tick(self) -> None:
        try:
            rows = self._get_rows()
        except Exception:
            rows = []

        # Mesma quantidade/ordem esperada — só atualiza texto/cor de cada
        # linha já existente. Se por algum motivo a quantidade mudar (ex.:
        # uma integração nova adicionada depois), reconstrói do zero.
        if len(rows) != len(self._row_widgets):
            for child in self._rows_frame.winfo_children():
                child.destroy()
            self._row_widgets = []
            self._build_rows(rows)
        else:
            for (dot, name_label, detail_label), (label, detail, ok) in zip(self._row_widgets, rows):
                dot.configure(text_color=theme.OK if ok else theme.TEXT_DIM)
                name_label.configure(text=label)
                detail_label.configure(text=detail)

        if self._root is not None:
            self._root.after(self.REFRESH_MS, self._tick)
