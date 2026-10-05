"""
Barra lateral de navegação — logo, páginas (Visão geral / Conversa) e
o botão de configurações no rodapé. Motivo de existir: a interface
antiga colocava TUDO (chat, painéis de sistema, controles) numa tela
só, disputando espaço; agora "Visão geral" (status/automação/módulos)
e "Conversa" (o chat de texto/voz) são páginas separadas, trocadas por
aqui, sem perder nenhuma função de nenhuma das duas.

Quem cria esta barra (interface/app.py) decide o que cada clique faz
via `on_navigate(key)`; este componente só cuida do desenho (destacar
a página ativa, mostrar/esconder o pontinho de "mensagem nova" ao lado
de "Conversa" quando uma resposta chega enquanto essa página não está
sendo vista).
"""
from __future__ import annotations

from typing import Callable, Iterable, Tuple

from interface import theme

# (chave da página, ícone, rótulo)
PageSpec = Tuple[str, str, str]


class Sidebar:
    WIDTH = 220

    def __init__(
        self,
        parent,
        ctk,
        *,
        pages: Iterable[PageSpec],
        on_navigate: Callable[[str], None],
        on_settings: Callable[[], None],
    ) -> None:
        self._ctk = ctk
        self._on_navigate = on_navigate
        self._active_key: str | None = None

        self.frame = ctk.CTkFrame(parent, fg_color=theme.PANEL, corner_radius=0, width=self.WIDTH)
        self.frame.pack_propagate(False)  # mantém a largura fixa mesmo com filhos menores/maiores

        header = ctk.CTkFrame(self.frame, fg_color="transparent")
        header.pack(fill="x", padx=18, pady=(22, 24))
        self._add_logo(header)

        nav = ctk.CTkFrame(self.frame, fg_color="transparent")
        nav.pack(fill="x", padx=12)

        self._buttons: dict[str, object] = {}
        self._badges: dict[str, object] = {}
        for key, icon, label in pages:
            row = ctk.CTkFrame(nav, fg_color="transparent")
            row.pack(fill="x", pady=3)

            btn = ctk.CTkButton(
                row,
                text=f"{icon}   {label}",
                anchor="w",
                height=42,
                corner_radius=8,
                fg_color="transparent",
                hover_color=theme.SURFACE_HOVER,
                text_color=theme.TEXT_DIM,
                font=("Segoe UI", 13),
                command=lambda k=key: self._on_navigate(k),
            )
            btn.pack(side="left", fill="x", expand=True)

            badge = ctk.CTkLabel(row, text="●", font=("Segoe UI", 9), text_color=theme.PANEL, width=14)
            badge.pack(side="right", padx=(0, 6))

            self._buttons[key] = btn
            self._badges[key] = badge

        # espaçador — empurra o botão de configurações pro rodapé da barra
        ctk.CTkFrame(self.frame, fg_color="transparent").pack(fill="both", expand=True)

        footer = ctk.CTkFrame(self.frame, fg_color="transparent")
        footer.pack(fill="x", padx=12, pady=18)
        ctk.CTkButton(
            footer,
            text="⚙   Configurar IA",
            anchor="w",
            height=40,
            corner_radius=8,
            fg_color=theme.SURFACE,
            hover_color=theme.SURFACE_HOVER,
            text_color=theme.TEXT,
            font=("Segoe UI", 13),
            command=on_settings,
        ).pack(fill="x")

    def set_active(self, key: str) -> None:
        self._active_key = key
        for k, btn in self._buttons.items():
            if k == key:
                btn.configure(fg_color=theme.PURPLE, text_color=theme.TEXT, hover_color=theme.PURPLE_HOVER)
                self.set_badge(k, False)  # abrir a página já limpa o aviso de mensagem nova dela
            else:
                btn.configure(fg_color="transparent", text_color=theme.TEXT_DIM, hover_color=theme.SURFACE_HOVER)

    def set_badge(self, key: str, show: bool) -> None:
        badge = self._badges.get(key)
        if badge is None:
            return
        badge.configure(text_color=theme.PURPLE_LIGHT if show else theme.PANEL)

    def _add_logo(self, header) -> None:
        """
        Ícone da logo (assets/logo_mark.png) + "JARVIS" ao lado. Se o
        arquivo não existir ou não puder ser carregado, cai pra só o
        texto — a interface nunca deve travar por causa disso.
        """
        from pathlib import Path

        ctk = self._ctk
        logo_path = Path(__file__).resolve().parent.parent.parent / "assets" / "logo_mark.png"
        try:
            from PIL import Image

            img = Image.open(logo_path)
            size = 32
            logo_image = ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
            icon_label = ctk.CTkLabel(header, image=logo_image, text="")
            icon_label.image = logo_image  # evita coleta de lixo do Tkinter
            icon_label.pack(side="left", padx=(0, 10))
        except Exception:
            pass

        from config.settings import settings

        ctk.CTkLabel(
            header, text=settings.jarvis_name.upper(), font=("Segoe UI", 17, "bold"), text_color=theme.TEXT
        ).pack(side="left")
