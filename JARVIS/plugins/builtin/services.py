"""Serviços opcionais: Slack, Figma, Stripe e conectores MCP."""
from __future__ import annotations

import os

from core.permissions import RiskLevel
from plugins.base import Plugin, PluginCapability
from plugins.mcp import make_mcp_plugin
from plugins.utils import env_status, request_json


def _slack_channels(limit: int = 100, **_: object):
    headers = {"Authorization": f"Bearer {os.getenv('SLACK_BOT_TOKEN','').strip()}"}
    return request_json(
        "GET", "https://slack.com/api/conversations.list",
        headers=headers, params={"limit": max(1, min(limit, 200))},
    )


def _slack_send(channel: str, text: str, **_: object):
    headers = {
        "Authorization": f"Bearer {os.getenv('SLACK_BOT_TOKEN','').strip()}",
        "Content-Type": "application/json",
    }
    return request_json(
        "POST", "https://slack.com/api/chat.postMessage",
        headers=headers, json_body={"channel": channel, "text": text},
    )


def _figma_file(file_key: str, **_: object):
    headers = {"X-Figma-Token": os.getenv("FIGMA_API_TOKEN", "").strip()}
    return request_json(
        "GET", f"https://api.figma.com/v1/files/{file_key}", headers=headers,
    )


def _figma_comments(file_key: str, **_: object):
    headers = {"X-Figma-Token": os.getenv("FIGMA_API_TOKEN", "").strip()}
    return request_json(
        "GET", f"https://api.figma.com/v1/files/{file_key}/comments", headers=headers,
    )


def _stripe_customers(limit: int = 10, **_: object):
    token = os.getenv("STRIPE_SECRET_KEY", "").strip()
    headers = {"Authorization": f"Bearer {token}"}
    return request_json(
        "GET", "https://api.stripe.com/v1/customers",
        headers=headers, params={"limit": max(1, min(limit, 100))},
    )


def _stripe_payment_intents(limit: int = 10, **_: object):
    token = os.getenv("STRIPE_SECRET_KEY", "").strip()
    headers = {"Authorization": f"Bearer {token}"}
    return request_json(
        "GET", "https://api.stripe.com/v1/payment_intents",
        headers=headers, params={"limit": max(1, min(limit, 100))},
    )


def register_plugins(registry) -> None:
    registry.register(Plugin(
        "slack", "Slack", "productivity", "Canais e mensagens Slack",
        {
            "channels.list": PluginCapability(
                "channels.list", "Lista canais Slack visíveis ao bot.",
                {"type":"object","properties":{"limit":{"type":"integer"}}},
                RiskLevel.LOW, _slack_channels,
            ),
            "message.send": PluginCapability(
                "message.send", "Envia mensagem em um canal Slack.",
                {"type":"object","properties":{"channel":{"type":"string"},"text":{"type":"string"}},"required":["channel","text"]},
                RiskLevel.MEDIUM, _slack_send, "Enviar mensagem Slack para {channel}",
            ),
        },
        lambda: env_status("SLACK_BOT_TOKEN", detail="bot configurado"),
        tags=("chat","team"),
    ))

    registry.register(Plugin(
        "figma", "Figma", "design", "Leitura de arquivos e comentários Figma",
        {
            "file.get": PluginCapability(
                "file.get", "Obtém estrutura de um arquivo Figma.",
                {"type":"object","properties":{"file_key":{"type":"string"}},"required":["file_key"]},
                RiskLevel.LOW, _figma_file,
            ),
            "comments.list": PluginCapability(
                "comments.list", "Lista comentários de um arquivo Figma.",
                {"type":"object","properties":{"file_key":{"type":"string"}},"required":["file_key"]},
                RiskLevel.LOW, _figma_comments,
            ),
        },
        lambda: env_status("FIGMA_API_TOKEN", detail="API configurada"),
        tags=("design","ui"),
    ))

    registry.register(Plugin(
        "stripe", "Stripe", "business", "Consulta de clientes e pagamentos Stripe",
        {
            "customers.list": PluginCapability(
                "customers.list", "Lista clientes recentes.",
                {"type":"object","properties":{"limit":{"type":"integer"}}},
                RiskLevel.LOW, _stripe_customers,
            ),
            "payments.list": PluginCapability(
                "payments.list", "Lista PaymentIntents recentes.",
                {"type":"object","properties":{"limit":{"type":"integer"}}},
                RiskLevel.LOW, _stripe_payment_intents,
            ),
        },
        lambda: env_status("STRIPE_SECRET_KEY", detail="API configurada"),
        tags=("payments","business"),
    ))

    registry.register(make_mcp_plugin("gitbook", "GitBook", "productivity", "GITBOOK"))
    registry.register(make_mcp_plugin("posthog", "PostHog", "observability", "POSTHOG"))
    registry.register(make_mcp_plugin("datadog", "Datadog", "observability", "DATADOG"))
