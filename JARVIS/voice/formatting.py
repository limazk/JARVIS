"""Prepara texto conversacional para leitura em voz alta, sem alterar o chat escrito."""
from __future__ import annotations

import re


def prepare_speech(text: str, max_chars: int = 2400) -> str:
    spoken = re.sub("(?s)" + chr(96) * 3 + ".*?" + chr(96) * 3,
                    "Trecho de código disponível na tela.", text)
    spoken = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", spoken)
    spoken = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", spoken)
    spoken = re.sub(r"https?://\S+", "no link informado", spoken)
    spoken = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", spoken)
    spoken = re.sub(r"(?m)^\s*[-*+]\s+", "", spoken)
    spoken = re.sub(r"(?m)^\s*\d+[.)]\s+", "", spoken)
    spoken = re.sub(r"[*_\u0060~]", "", spoken)
    spoken = re.sub(r"[|]+", ". ", spoken)
    spoken = " ".join(spoken.split())
    if len(spoken) > max_chars:
        candidate = spoken[:max_chars].rsplit(". ", 1)
        spoken = (candidate[0] if len(candidate) > 1 and len(candidate[0]) > max_chars // 2
                  else spoken[:max_chars].rsplit(" ", 1)[0])
        spoken += ". O restante está disponível na tela."
    return spoken
