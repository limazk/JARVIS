"""
Calculadora segura — seção 23 do spec.

Nunca usa eval() com entrada do usuário. Em vez disso, faz o parse
da expressão com o módulo `ast` e só permite operações aritméticas
básicas — qualquer outra coisa (imports, chamadas de função, nomes
de variável, etc.) é rejeitada antes de ser avaliada.
"""
from __future__ import annotations

import ast
import operator
import re

from core.permissions import RiskLevel
from tools.base import Tool, ToolResult

_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(node: ast.AST):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("expressão contém algo que não é uma operação matemática simples")


def _normalize(expr: str) -> str:
    expr = expr.lower().strip()

    # "12% de 1500" -> (12/100)*1500  (precisa vir antes das outras trocas)
    pct = re.match(r"^([\d.,]+)\s*%\s*de\s*([\d.,]+)$", expr)
    if pct:
        a = pct.group(1).replace(",", ".")
        b = pct.group(2).replace(",", ".")
        return f"({a}/100)*{b}"

    expr = expr.replace(" vezes ", "*").replace(" x ", "*")
    expr = expr.replace(" dividido por ", "/").replace(" dividir por ", "/").replace(" dividido ", "/")
    expr = expr.replace(" mais ", "+").replace(" menos ", "-")
    expr = expr.replace(",", ".")
    expr = expr.replace("%", "/100")
    return expr


def calculate(expression: str, **_: object) -> ToolResult:
    normalized = _normalize(expression)
    try:
        tree = ast.parse(normalized, mode="eval")
        result = _safe_eval(tree.body)
    except Exception:
        return ToolResult(success=False, message=f"Não consegui calcular '{expression}'.")

    if isinstance(result, float) and result.is_integer():
        result = int(result)
    return ToolResult(success=True, message=f"O resultado é {result}.", data={"result": result})


def register(registry) -> None:
    registry.register(Tool(
        name="calculate",
        description="Calcula uma expressão matemática: soma, subtração, multiplicação, divisão, potência ou porcentagem.",
        parameters={
            "type": "object",
            "properties": {"expression": {"type": "string", "description": "Ex.: '150 vezes 22' ou '12% de 1500'"}},
            "required": ["expression"],
        },
        risk_level=RiskLevel.LOW,
        handler=calculate,
    ))
