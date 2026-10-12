"""Capture a pergunta após o chamado com diagnóstico claro e uma segunda tentativa.

O reconhecimento da wake word não prova que o comando seguinte foi
transcrito. Este módulo impede que o terminal descarte silenciosamente
falhas de reconhecimento, sem disparar chamadas de LLM.
"""
from __future__ import annotations

import logging
from typing import Callable

from voice.listener import feedback_message

logger = logging.getLogger("jarvis.voice.session")


def capture_command(
    listener,
    *,
    phrase_time_limit: float,
    on_retry: Callable[[str], None] | None = None,
) -> str | None:
    """Captura o comando com no máximo duas tentativas após a saudação.

    Só repete quando houve silêncio ou a fala não foi entendida. Não insiste
    com o microfone indisponível ou ocupado e nunca executa uma ferramenta
    quando o reconhecimento falha.
    """
    for attempt in range(2):
        outcome = listener.listen_once_detailed(
            phrase_time_limit=phrase_time_limit
        )
        if outcome.text:
            return outcome.text.strip() or None

        feedback = feedback_message(outcome)
        if feedback:
            print(f"[escuta: {outcome.reason}] {feedback}", flush=True)
        else:
            print(f"[escuta: {outcome.reason}] Nenhuma pergunta capturada.", flush=True)
        logger.info("Falha na captura do comando de voz: %s", outcome.reason)

        if attempt == 0 and outcome.reason in {"no_speech", "not_understood"}:
            prompt = "Não ouvi sua pergunta. Pode repetir?"
            if on_retry is not None:
                try:
                    on_retry(prompt)
                except Exception:
                    logger.warning("Não consegui reproduzir o aviso de nova tentativa.", exc_info=True)
            print("(ouvindo novamente...)", flush=True)
            continue

        return None
    return None
