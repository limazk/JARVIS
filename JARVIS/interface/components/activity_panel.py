"""
Painel de ATIVIDADE — lista as últimas ações do Jarvis (seções 10/50/55),
lidas diretamente da tabela `activities` do SQLite (memory/database.py).
"""
from __future__ import annotations

from datetime import datetime

from interface import theme


class ActivityPanel:
    REFRESH_MS = 3000

    def __init__(self, parent, ctk) -> None:
        self.frame = ctk.CTkFrame(parent, fg_color=theme.PANEL, corner_radius=12)
        ctk.CTkLabel(self.frame, text="ATIVIDADE", font=("Segoe UI", 12, "bold"), text_color=theme.TEXT_DIM).pack(
            anchor="w", padx=14, pady=(12, 4)
        )
        self.list_box = ctk.CTkTextbox(self.frame, fg_color=theme.SURFACE, text_color=theme.TEXT, font=("Consolas", 12))
        self.list_box.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self.list_box.configure(state="disabled")
        self._root = None

    def start(self, root) -> None:
        self._root = root
        self._tick()

    def _tick(self) -> None:
        try:
            from memory.database import recent_activities

            rows = recent_activities(limit=30)
            self.list_box.configure(state="normal")
            self.list_box.delete("1.0", "end")
            for row in reversed(rows):
                try:
                    ts = datetime.fromisoformat(row["created_at"]).strftime("%H:%M")
                except Exception:
                    ts = "--:--"
                self.list_box.insert("end", f"{ts}  {row['description']}\n")
            self.list_box.configure(state="disabled")
        except Exception:
            pass

        if self._root is not None:
            self._root.after(self.REFRESH_MS, self._tick)
