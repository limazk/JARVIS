"""
Tela de configuração inicial de IA — parte da ETAPA EXE-1 (preparação
para empacotar o Jarvis como .exe).

Um `.exe` de verdade não deveria exigir que a pessoa abra o `.env` num
editor de texto pra colocar uma chave de API. Este diálogo deixa
escolher o provedor (Gemini/Groq grátis, Claude/OpenAI pagos, ou
Ollama 100% local) e colar a chave direto na interface — ele só chama
`config.settings.save_env_values`, então o resultado é exatamente o
mesmo `.env` de sempre; quem preferir editar manualmente continua
podendo.
"""
from __future__ import annotations

from typing import Callable

from interface import theme

# (valor salvo em LLM_PROVIDER, texto do botão, variável de ambiente da
#  chave — None quando o provedor não precisa de chave, link pra gerar)
_PROVIDERS: list[tuple[str, str, "str | None", str]] = [
    ("gemini", "Gemini (Google) — grátis, sem cartão", "GEMINI_API_KEY", "https://aistudio.google.com/apikey"),
    ("groq", "Groq — grátis, sem cartão, respostas rápidas", "GROQ_API_KEY", "https://console.groq.com/keys"),
    ("claude", "Claude (Anthropic) — pago por uso", "ANTHROPIC_API_KEY", "https://console.anthropic.com"),
    ("openai", "OpenAI (ChatGPT) — pago por uso", "OPENAI_API_KEY", "https://platform.openai.com/api-keys"),
    ("local", "Ollama — 100% local, grátis, sem chave", None, "https://ollama.com"),
]


class SetupDialog:
    def __init__(self, root, ctk, on_saved: Callable[[], None]) -> None:
        from config.settings import save_env_values, settings

        self._ctk = ctk
        self._on_saved = on_saved
        self._save_env_values = save_env_values

        valid_values = [p[0] for p in _PROVIDERS]
        default_provider = settings.llm_provider if settings.llm_provider in valid_values else "gemini"

        self.dialog = ctk.CTkToplevel(root)
        self.dialog.title("Configurar IA do Jarvis")
        self.dialog.geometry("460x460")
        self.dialog.configure(fg_color=theme.PANEL)
        self.dialog.attributes("-topmost", True)
        self.dialog.grab_set()

        ctk.CTkLabel(
            self.dialog, text="Escolha o provedor de IA", font=("Segoe UI", 15, "bold"), text_color=theme.TEXT,
        ).pack(padx=20, pady=(20, 4), anchor="w")
        ctk.CTkLabel(
            self.dialog,
            text="Sem isso, o Jarvis funciona só com comandos diretos (sem conversa livre).\n"
            "Você pode trocar isso depois a qualquer momento.",
            font=("Segoe UI", 11), text_color=theme.TEXT_DIM, justify="left",
        ).pack(padx=20, pady=(0, 12), anchor="w")

        self._provider_var = ctk.StringVar(value=default_provider)
        for value, label, _key, _url in _PROVIDERS:
            ctk.CTkRadioButton(
                self.dialog, text=label, variable=self._provider_var, value=value,
                command=self._on_provider_change,
            ).pack(padx=20, pady=4, anchor="w")

        self._hint_label = ctk.CTkLabel(
            self.dialog, text="", font=("Segoe UI", 11), text_color=theme.PURPLE_LIGHT, wraplength=410, justify="left",
        )
        self._hint_label.pack(padx=20, pady=(12, 4), anchor="w")

        self._key_entry = ctk.CTkEntry(self.dialog, width=410, placeholder_text="Cole sua chave de API aqui")
        self._key_entry.pack(padx=20, pady=(4, 16))

        self._status_label = ctk.CTkLabel(self.dialog, text="", font=("Segoe UI", 11))
        self._status_label.pack(padx=20, pady=(0, 8))

        btn_row = ctk.CTkFrame(self.dialog, fg_color="transparent")
        btn_row.pack(pady=8)
        ctk.CTkButton(
            btn_row, text="Salvar", fg_color=theme.PURPLE, hover_color=theme.PURPLE_HOVER, command=self._save,
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            btn_row, text="Agora não", fg_color=theme.SURFACE, hover_color=theme.SURFACE_HOVER, command=self.dialog.destroy,
        ).pack(side="left", padx=8)

        self._on_provider_change()

    def _current_entry(self) -> tuple:
        value = self._provider_var.get()
        return next(p for p in _PROVIDERS if p[0] == value)

    def _on_provider_change(self) -> None:
        _value, _label, key_name, url = self._current_entry()
        if key_name is None:
            self._hint_label.configure(
                text=f"Não precisa de chave — instale o Ollama em {url} e baixe um modelo "
                f"(ex.: ollama pull llama3.1) antes de usar."
            )
            self._key_entry.configure(state="disabled", placeholder_text="Não é necessário para o Ollama")
        else:
            grátis = "grátis, sem cartão — " if key_name in {"GEMINI_API_KEY", "GROQ_API_KEY"} else ""
            self._hint_label.configure(text=f"Gere sua chave ({grátis}sem custo pra testar) em {url}")
            self._key_entry.configure(state="normal", placeholder_text="Cole sua chave de API aqui")
        self._status_label.configure(text="")

    def _save(self) -> None:
        value, _label, key_name, _url = self._current_entry()

        to_save = {"LLM_PROVIDER": value}
        if key_name is not None:
            key = self._key_entry.get().strip()
            if not key:
                self._status_label.configure(text="Cole a chave antes de salvar.", text_color=theme.ERROR)
                return
            to_save[key_name] = key

        try:
            self._save_env_values(to_save)
        except OSError as exc:
            self._status_label.configure(text=f"Não consegui salvar: {exc}", text_color=theme.ERROR)
            return

        self._status_label.configure(text="Salvo! Recarregando...", text_color=theme.PURPLE_LIGHT)
        self.dialog.after(500, self._finish)

    def _finish(self) -> None:
        self.dialog.destroy()
        self._on_saved()
