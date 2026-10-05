"""Testes de tools/registry.py — o registro central de ferramentas."""
from core.permissions import RiskLevel
from tools.base import Tool, ToolResult
from tools.registry import ToolRegistry


def _tool(name: str) -> Tool:
    return Tool(
        name=name,
        description=f"tool de teste {name}",
        parameters={"type": "object", "properties": {}},
        risk_level=RiskLevel.LOW,
        handler=lambda **_: ToolResult(success=True, message="ok"),
    )


def _registry_com(*names: str) -> ToolRegistry:
    registry = ToolRegistry()
    for name in names:
        registry.register(_tool(name))
    return registry


def test_as_llm_tool_schemas_sem_prioridade_mantem_ordem_de_registro():
    registry = _registry_com("a", "b", "c")

    schemas = registry.as_llm_tool_schemas()

    assert [s["name"] for s in schemas] == ["a", "b", "c"]


def test_as_llm_tool_schemas_prioriza_sem_remover_nenhuma():
    registry = _registry_com("a", "b", "c", "d")

    schemas = registry.as_llm_tool_schemas(prioritize=("c", "a"))
    nomes = [s["name"] for s in schemas]

    # "c" e "a" vêm primeiro (mantendo a ordem relativa entre si e entre
    # os demais, já que o sort é estável); nada desaparece.
    assert nomes[:2] == ["a", "c"]
    assert set(nomes) == {"a", "b", "c", "d"}
    assert len(nomes) == 4


def test_as_llm_tool_schemas_prioridade_com_nome_inexistente_nao_quebra():
    registry = _registry_com("a", "b")

    schemas = registry.as_llm_tool_schemas(prioritize=("nao_existe",))

    assert {s["name"] for s in schemas} == {"a", "b"}
