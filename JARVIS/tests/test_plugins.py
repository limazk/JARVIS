"""Testes da camada de plugins sem acessar serviços externos."""
from core.permissions import RiskLevel
from plugins.bridge import attach_plugin_registry
from plugins.registry import build_default_plugin_registry
from tools.registry import ToolRegistry


def test_registry_carrega_plugins_principais(monkeypatch):
    monkeypatch.delenv("NOTION_API_KEY", raising=False)
    tools = ToolRegistry()
    plugins = build_default_plugin_registry(tools)
    ids = set(plugins.ids())
    expected = {
        "github", "filesystem", "shell", "docker", "supabase", "render", "vercel",
        "trello", "notion", "gmail", "calendar", "drive", "browser",
        "tavily", "exa", "slack", "figma", "gitbook", "posthog", "datadog", "stripe",
    }
    assert expected.issubset(ids)


def test_notion_fica_disponivel_com_token(monkeypatch):
    monkeypatch.setenv("NOTION_API_KEY", "secret_test")
    tools = ToolRegistry()
    plugins = build_default_plugin_registry(tools)
    notion = plugins.get("notion")
    assert notion is not None
    assert notion.status().available is True
    assert notion.capability("search").risk_level == RiskLevel.LOW
    assert notion.capability("page.create").risk_level == RiskLevel.MEDIUM


def test_trello_escrita_exige_risco_medio(monkeypatch):
    monkeypatch.setenv("TRELLO_API_KEY", "key")
    monkeypatch.setenv("TRELLO_TOKEN", "token")
    plugins = build_default_plugin_registry(ToolRegistry())
    trello = plugins.get("trello")
    assert trello is not None
    assert trello.status().available is True
    assert trello.capability("card.create").risk_level == RiskLevel.MEDIUM
    assert trello.capability("card.move").risk_level == RiskLevel.MEDIUM


def test_bridge_registra_tools_meta():
    tools = ToolRegistry()
    plugins = attach_plugin_registry(tools)
    assert tools.plugin_registry is plugins
    assert tools.get("list_plugins") is not None
    assert tools.get("plugin_status") is not None
    assert tools.get("plugin_execute") is not None


def test_plugin_desconhecido_falha_fechado():
    plugins = build_default_plugin_registry(ToolRegistry())
    result = plugins.invoke("nao-existe", "qualquer", {})
    assert result.success is False


def test_mcp_plugins_dependem_de_url(monkeypatch):
    monkeypatch.delenv("GITBOOK_MCP_URL", raising=False)
    plugins = build_default_plugin_registry(ToolRegistry())
    gitbook = plugins.get("gitbook")
    assert gitbook is not None
    assert gitbook.status().available is False
    monkeypatch.setenv("GITBOOK_MCP_URL", "https://example.invalid/mcp")
    plugins = build_default_plugin_registry(ToolRegistry())
    assert plugins.get("gitbook").status().available is True
