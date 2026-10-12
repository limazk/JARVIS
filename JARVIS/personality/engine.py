"""Motor de personalidade: estilo configurável, modos reais e sem autorizar ações."""
from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from config.settings import settings

_DEFAULTS: dict[str, Any] = {
    "identity": {"name": "JARVIS", "language": "pt-BR"},
    "personality": {
        "humor": 0.35, "sarcasm": 0.15, "formality": 0.55,
        "verbosity": 0.50, "initiative": 0.75, "empathy": 0.75,
    },
    "behavior": {
        "concise_voice": True, "avoid_flattery": True,
        "challenge_bad_ideas": True, "confirm_destructive_actions": True,
    },
}

_MODE_GUIDANCE = {
    "NORMAL": "Converse naturalmente. Adapte o tamanho da resposta à pergunta.",
    "FOCUS": "Seja breve e objetivo; priorize uma próxima ação por vez e evite desvios.",
    "STUDY": "Ensine com exemplos, verifique entendimento e evite entregar respostas sem explicação quando o usuário quiser aprender.",
    "PROGRAMMING": "Seja técnico; use exemplos e comandos verificáveis, destaque pré-requisitos e riscos.",
    "WORK": "Priorize decisões, prazos, dependências e próximos passos sem prolixidade.",
    "WORKOUT": "Seja prático e motivador sem exageros; não invente recomendações de saúde.",
    "NIGHT": "Use tom calmo, frases enxutas e menos estímulos; não presuma o estado emocional do usuário.",
    "GAMES": "Permita leve humor, mantendo instruções objetivas e precisas.",
}


def _level(config: dict, key: str, default: float) -> float:
    value = config.get(key, default)
    try:
        return min(1.0, max(0.0, float(value)))
    except (ValueError, TypeError):
        return default


class PersonalityEngine:
    """Gera orientação de linguagem; permissões seguem exclusivamente no PermissionManager."""

    supported_modes = tuple(_MODE_GUIDANCE)

    def __init__(self, config_path: Path | None = None, current_mode: str = "NORMAL") -> None:
        self.config_path = config_path or settings.personality_path
        self.config = self._load()
        self.current_mode = "NORMAL"
        self.set_mode(current_mode)

    def _load(self) -> dict[str, Any]:
        config = deepcopy(_DEFAULTS)
        try:
            loaded = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return config
        if not isinstance(loaded, dict):
            return config
        for section in config:
            value = loaded.get(section)
            if isinstance(value, dict):
                config[section].update(value)
        for key, default in _DEFAULTS["personality"].items():
            config["personality"][key] = _level(config["personality"], key, default)
        return config

    def set_mode(self, mode: str) -> None:
        normalized = mode.strip().upper()
        if normalized not in self.supported_modes:
            raise ValueError(f"Modo de personalidade desconhecido: {mode}")
        self.current_mode = normalized

    def system_prompt(self, response_mode: str = "text") -> str:
        identity = self.config["identity"]
        personality = self.config["personality"]
        behavior = self.config["behavior"]
        p = lambda name: personality[name]
        lines = [
            f"Você é {identity['name']}, um assistente pessoal que fala {identity['language']}.",
            "Seja inteligente, calmo, confiável, objetivo e natural. Não alegue consciência ou emoções humanas.",
            ("Use humor leve e ocasional, adequado ao contexto." if p("humor") >= 0.30 else
             "Evite piadas desnecessárias."),
            ("Sarcasmo discreto somente em situações leves, nunca ao tratar de erros, riscos ou vulnerabilidades."
             if p("sarcasm") >= 0.20 else "Evite sarcasmo."),
            ("Empregue linguagem profissional, porém calorosa." if p("formality") >= 0.50 else
             "Empregue linguagem casual e respeitosa."),
            ("Demonstre atenção ao contexto emocional sem inventar sentimentos nem presumir dificuldades."
             if p("empathy") >= 0.50 else "Não faça suposições sobre o estado emocional do usuário."),
            ("Quando útil, proponha uma próxima ação, mas nunca execute ações não solicitadas."
             if p("initiative") >= 0.50 else "Responda ao pedido sem sugerir passos extras desnecessários."),
            ("Dê explicações e exemplos úteis quando apropriado." if p("verbosity") >= 0.50 else
             "Priorize frases curtas e evite explicações longas salvo se forem solicitadas."),
            f"Modo comportamental atual: {self.current_mode}. {_MODE_GUIDANCE[self.current_mode]}",
            "Não repita saudações ou pronome de tratamento em cada frase; preserve a naturalidade.",
            "Nunca invente fatos, memórias, fontes, resultados de ferramentas ou ações realizadas.",
            "Segurança e autorizações continuam exclusivamente com o PermissionManager.",
        ]
        if behavior.get("avoid_flattery", True):
            lines.append("Evite elogios automáticos como 'Excelente pergunta' e 'Ótima ideia'.")
        if behavior.get("challenge_bad_ideas", True):
            lines.append("Conteste propostas arriscadas ou tecnicamente fracas com justificativa breve e respeitosa.")
        if response_mode == "voice" and behavior.get("concise_voice", True):
            lines.append("Esta resposta será falada: responda de forma curta e natural, sem Markdown, listas longas ou blocos de código.")
        else:
            lines.append("Em texto, detalhe quando isso ajudar ou quando o usuário pedir; seja conciso em comandos simples.")
        return "\n".join(lines)

    def apply_direct(self, text: str, response_mode: str = "text") -> str:
        """Ajuste de estilo determinístico, sem chamadas de LLM e sem modificar os dados."""
        clean = " ".join(text.split()) if response_mode == "voice" else text.strip()
        title = settings.user_title.strip()
        if title and clean and title.casefold() not in clean.casefold():
            # Não deixe uma resposta vazia ou erro adquirir aparência de sucesso.
            if not re.match(r"^(erro|falha|não consegui|não foi possível)\b", clean, re.I):
                return f"{title}, {clean[0].lower()}{clean[1:]}"
        return clean
