"""Personalidade configurável, independente da camada de permissões."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from config.settings import settings


_DEFAULTS: dict[str, Any] = {
    "identity": {"name": "JARVIS", "language": "pt-BR"},
    "personality": {"humor": 0.30, "sarcasm": 0.10, "formality": 0.50, "verbosity": 0.30, "initiative": 0.65},
    "behavior": {"concise_voice": True, "avoid_flattery": True, "challenge_bad_ideas": True,
                 "confirm_destructive_actions": True},
}


class PersonalityEngine:
    """Compõe instruções de estilo. Nunca autoriza nem executa ferramentas."""

    supported_modes = ("NORMAL", "FOCUS", "STUDY", "PROGRAMMING", "WORK", "WORKOUT", "NIGHT", "GAMES")

    def __init__(self, config_path: Path | None = None, current_mode: str = "NORMAL") -> None:
        self.config_path = config_path or settings.personality_path
        self.config = self._load()
        self.current_mode = "NORMAL"
        self.set_mode(current_mode)

    def _load(self) -> dict[str, Any]:
        config = deepcopy(_DEFAULTS)
        try:
            loaded = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return config
        for section in config:
            value = loaded.get(section)
            if isinstance(value, dict):
                config[section].update(value)
        return config

    def set_mode(self, mode: str) -> None:
        normalized = mode.strip().upper()
        if normalized not in self.supported_modes:
            raise ValueError(f"Modo de personalidade desconhecido: {mode}")
        self.current_mode = normalized

    def system_prompt(self, response_mode: str = "text") -> str:
        identity = self.config["identity"]
        behavior = self.config["behavior"]
        voice = response_mode == "voice"
        lines = [
            f"Você é {identity['name']}, um assistente pessoal que fala {identity['language']}.",
            "Sua personalidade é inteligente, calma, objetiva, confiante sem arrogância, natural e levemente sofisticada.",
            "Use humor moderado e sarcasmo baixo. Não seja bajulador nem excessivamente formal.",
            "Evite bordões automáticos como 'Excelente pergunta', 'Ótima ideia', 'Com certeza' e emojis gratuitos.",
            "Se uma ideia for ruim ou arriscada, explique isso com franqueza e brevidade.",
            "Personalidade nunca substitui segurança: ações destrutivas continuam dependendo do PermissionManager.",
            f"Modo comportamental atual: {self.current_mode}. O modo está reservado para ajustes futuros; não invente capacidades.",
        ]
        if voice and behavior.get("concise_voice", True):
            lines.append("Esta resposta será falada: responda de forma curta e natural, sem Markdown, listas longas ou blocos de código.")
        else:
            lines.append("Em texto, detalhe quando isso ajudar ou quando o usuário pedir; mantenha concisão em comandos simples.")
        return "\n".join(lines)

    def apply_direct(self, text: str, response_mode: str = "text") -> str:
        """Aplica o estilo mínimo às respostas determinísticas, sem chamar LLM."""
        clean = " ".join(text.split()) if response_mode == "voice" else text.strip()
        title = settings.user_title.strip()
        if title and clean and title.casefold() not in clean.casefold():
            return f"{title}, {clean[0].lower()}{clean[1:]}"
        return clean
