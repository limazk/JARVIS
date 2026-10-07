"""Cliente MCP Streamable HTTP mínimo para plugins opcionais.

Permite conectar servidores MCP sem expor credenciais aos workers. O suporte é
deliberadamente genérico: configure URL/token e use tools.list/tool.call.
"""
from __future__ import annotations

import json
import os
import uuid

from core.permissions import RiskLevel
from plugins.base import Plugin, PluginCapability, PluginResult, PluginStatus


class MCPHttpClient:
    def __init__(self, url: str, token: str = "") -> None:
        self.url = url
        self.token = token
        self.session_id = ""
        self._id = 0

    def _headers(self) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-06-18",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        return headers

    @staticmethod
    def _decode(response):
        ctype = response.headers.get("content-type", "")
        if "text/event-stream" in ctype:
            events = []
            for line in response.text.splitlines():
                if line.startswith("data:"):
                    raw = line[5:].strip()
                    if raw:
                        try:
                            events.append(json.loads(raw))
                        except json.JSONDecodeError:
                            pass
            return events[-1] if events else {}
        return response.json()

    def _post(self, method: str, params: dict | None = None, notification: bool = False):
        import requests
        self._id += 1
        payload = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        if not notification:
            payload["id"] = self._id
        response = requests.post(self.url, headers=self._headers(), json=payload, timeout=30)
        response.raise_for_status()
        sid = response.headers.get("Mcp-Session-Id")
        if sid:
            self.session_id = sid
        if notification:
            return {}
        return self._decode(response)

    def initialize(self) -> None:
        if self.session_id:
            return
        self._post("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "nexus", "version": "0.5"},
        })
        self._post("notifications/initialized", notification=True)

    def list_tools(self) -> dict:
        self.initialize()
        return self._post("tools/list", {}).get("result", {})

    def call_tool(self, name: str, arguments: dict) -> dict:
        self.initialize()
        return self._post("tools/call", {"name": name, "arguments": arguments}).get("result", {})


def make_mcp_plugin(plugin_id: str, name: str, category: str, env_prefix: str) -> Plugin:
    url_key = f"{env_prefix}_MCP_URL"
    token_key = f"{env_prefix}_MCP_TOKEN"

    def status() -> PluginStatus:
        url = os.getenv(url_key, "").strip()
        return PluginStatus(bool(url), url or f"configure {url_key}")

    def list_tools(**_: object) -> PluginResult:
        try:
            client = MCPHttpClient(os.getenv(url_key, ""), os.getenv(token_key, ""))
            data = client.list_tools()
            return PluginResult(True, f"Ferramentas MCP de {name} carregadas.", data)
        except Exception as exc:
            return PluginResult(False, f"MCP {name} falhou: {exc}")

    def call(name: str, arguments: dict | None = None, **_: object) -> PluginResult:
        try:
            client = MCPHttpClient(os.getenv(url_key, ""), os.getenv(token_key, ""))
            data = client.call_tool(name, arguments or {})
            return PluginResult(True, f"MCP {name}.{name} executado.", data)
        except Exception as exc:
            return PluginResult(False, f"MCP {name} falhou: {exc}")

    return Plugin(
        plugin_id,
        name,
        category,
        f"Integração MCP genérica com {name}.",
        {
            "tools.list": PluginCapability(
                "tools.list", "Lista ferramentas publicadas pelo servidor MCP.",
                {"type": "object", "properties": {}}, RiskLevel.LOW, list_tools,
            ),
            "tool.call": PluginCapability(
                "tool.call", "Executa uma ferramenta MCP pelo nome.",
                {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "arguments": {"type": "object", "additionalProperties": True},
                    },
                    "required": ["name"],
                },
                RiskLevel.MEDIUM,
                call,
                confirmation_template="Executar ferramenta MCP {name}",
            ),
        },
        status,
        tags=("mcp",),
    )
