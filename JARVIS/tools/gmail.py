"""
Gmail — ler e-mails não lidos e mandar e-mail direto do Jarvis. Parte
da integração Google (item do roadmap "Gmail/Calendar/Drive"); setup
completo e compartilhado com Calendar/Drive em tools/google_auth.py e
no README, seção "Google — Gmail/Calendar/Drive".
"""
from __future__ import annotations

import base64
from email.mime.text import MIMEText

from core.permissions import RiskLevel
from tools.base import Tool, ToolResult
from tools.google_auth import get_google_service, no_google_credentials_result


def list_unread_emails(limit: int = 5, **_: object) -> ToolResult:
    service = get_google_service("gmail", "v1")
    if service is None:
        return no_google_credentials_result()
    try:
        resp = (
            service.users()
            .messages()
            .list(userId="me", labelIds=["UNREAD", "INBOX"], maxResults=limit)
            .execute()
        )
        messages = resp.get("messages", [])
        if not messages:
            return ToolResult(success=True, message="Nenhum e-mail não lido na caixa de entrada.")

        lines = []
        for m in messages:
            full = (
                service.users()
                .messages()
                .get(userId="me", id=m["id"], format="metadata", metadataHeaders=["From", "Subject"])
                .execute()
            )
            headers = {h["name"]: h["value"] for h in full.get("payload", {}).get("headers", [])}
            lines.append(f"- {headers.get('From', '?')}: {headers.get('Subject', '(sem assunto)')}")
        return ToolResult(success=True, message="E-mails não lidos:\n" + "\n".join(lines))
    except Exception as exc:
        return ToolResult(success=False, message=f"Não consegui consultar o Gmail: {exc}")


def send_email(to: str, subject: str, body: str, **_: object) -> ToolResult:
    service = get_google_service("gmail", "v1")
    if service is None:
        return no_google_credentials_result()
    try:
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return ToolResult(success=True, message=f"E-mail enviado para {to}.")
    except Exception as exc:
        return ToolResult(success=False, message=f"Não consegui enviar o e-mail: {exc}")


def register(registry) -> None:
    registry.register(Tool(
        name="list_unread_emails",
        description="Lista os e-mails não lidos mais recentes da caixa de entrada do Gmail (remetente e assunto).",
        parameters={
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "Quantos e-mails, padrão 5"}},
        },
        risk_level=RiskLevel.LOW,
        handler=list_unread_emails,
    ))
    registry.register(Tool(
        name="send_email",
        description="Manda um e-mail pelo Gmail do usuário. Sempre exige confirmação antes de enviar.",
        parameters={
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Endereço de e-mail do destinatário"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["to", "subject", "body"],
        },
        risk_level=RiskLevel.MEDIUM,
        handler=send_email,
        confirmation_template="Mandar e-mail para {to} com assunto '{subject}'",
    ))
