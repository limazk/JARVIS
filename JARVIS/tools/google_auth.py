"""
Autenticação compartilhada com as APIs do Google (Gmail, Calendar,
Drive) — item do roadmap ("Gmail/Calendar/Drive"). Um único login/
token cobre as três, então essa parte fica separada de tools/gmail.py,
tools/gcalendar.py e tools/gdrive.py, que só chamam `get_google_service`.

Fluxo (mesmo padrão OAuth "app instalado" já usado pro Spotify em
tools/spotify.py, recomendado pelo próprio Google pra apps de
desktop): na primeira chamada, abre o navegador pra você autorizar;
depois disso fica em cache (`google_token.json`, ao lado do `.env`) e
não pede de novo — EXCETO que, enquanto o app não passar pela
verificação do Google (só faz sentido pra apps públicos, não pra um
assistente pessoal seu), o Google expira esse acesso sozinho a cada 7
dias; quando isso acontecer, o Jarvis detecta e abre o navegador de
novo automaticamente, sem travar nem dar erro feio.

Setup completo (crie o projeto grátis, ative as APIs, baixe o arquivo
`google_credentials.json`) está no README, seção "Google —
Gmail/Calendar/Drive".
"""
from __future__ import annotations

import logging
from typing import Optional

from config.settings import settings
from tools.base import ToolResult

logger = logging.getLogger("jarvis.google_auth")

# Um escopo por API/permissão usada pelos tools/gmail.py, gcalendar.py e
# gdrive.py — pedidos todos juntos na mesma autorização, pra só precisar
# logar uma vez em vez de uma vez por serviço.
_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/drive.readonly",
]

_credentials_cache = None  # guarda a credencial autenticada entre chamadas nesta execução


def _credentials_path():
    return settings.base_dir / "google_credentials.json"


def _token_path():
    return settings.base_dir / "google_token.json"


def _get_credentials():
    """Devolve uma Credentials válida, ou None se faltar configuração/biblioteca."""
    global _credentials_cache
    if _credentials_cache is not None and _credentials_cache.valid:
        return _credentials_cache

    if not _credentials_path().exists():
        return None

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        return None

    creds = None
    token_path = _token_path()
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), _SCOPES)
        except Exception:
            creds = None

    if creds and not creds.valid and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            logger.info("Token do Google expirou e não deu pra renovar sozinho — reautenticando do zero.")
            creds = None

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(_credentials_path()), _SCOPES)
        creds = flow.run_local_server(port=0)

    token_path.write_text(creds.to_json(), encoding="utf-8")
    _credentials_cache = creds
    return creds


def get_google_service(api_name: str, api_version: str) -> Optional[object]:
    """Devolve um serviço autenticado (`googleapiclient.discovery.build(...)`), ou None."""
    creds = _get_credentials()
    if creds is None:
        return None
    try:
        from googleapiclient.discovery import build
    except ImportError:
        return None
    return build(api_name, api_version, credentials=creds, cache_discovery=False)


def no_google_credentials_result() -> ToolResult:
    return ToolResult(
        success=False,
        message=(
            "Preciso do arquivo google_credentials.json configurado pra falar com o Google "
            "(Gmail/Calendar/Drive) — veja o README, seção 'Google — Gmail/Calendar/Drive', "
            "pra gerar o seu grátis em alguns minutos."
        ),
    )
