"""Ponto público da integração JARVIS → ROTINA.

A implementação vive em integrations/rotina.py; este módulo mantém o nome
histórico da ponte sem duplicar chamadas HTTP.
"""
from integrations.rotina import (
    RotinaAuthError,
    RotinaClient,
    RotinaError,
    RotinaProcessManager,
)

__all__ = ["RotinaClient", "RotinaProcessManager", "RotinaError", "RotinaAuthError"]
