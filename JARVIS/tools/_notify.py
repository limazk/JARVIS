"""
Notificação nativa do Windows — seção 39 do spec.

Usado por reminders.py e timers.py. Tenta `win11toast` (nativo do
Windows 10/11); se não estiver disponível (outro SO, ou não
instalado), cai para um print no console — nunca lança exceção
para quem chamou.
"""
from __future__ import annotations

import logging
import platform

logger = logging.getLogger("jarvis.notify")


def notify(title: str, message: str) -> None:
    if platform.system() == "Windows":
        try:
            from win11toast import notify as win_notify

            win_notify(title, message)
            return
        except Exception as exc:
            logger.debug("win11toast indisponível (%s), usando fallback de console.", exc)

    print(f"\n🔔 [{title}] {message}\n")


def play_alert_sound() -> None:
    """Toca um bipe simples (usado pelos timers). Silencioso fora do Windows."""
    if platform.system() == "Windows":
        try:
            import winsound

            winsound.MessageBeep()
        except Exception:
            pass
