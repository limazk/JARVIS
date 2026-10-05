"""Testes da calculadora segura (tools/calculator.py) — seção 43 do spec."""
from tools.calculator import calculate


def test_soma_simples():
    result = calculate(expression="2 + 2")
    assert result.success
    assert result.data["result"] == 4


def test_multiplicacao_por_extenso():
    result = calculate(expression="150 vezes 22")
    assert result.success
    assert result.data["result"] == 3300


def test_porcentagem():
    result = calculate(expression="12% de 1500")
    assert result.success
    assert result.data["result"] == 180


def test_divisao_por_extenso():
    result = calculate(expression="400 dividido por 6")
    assert result.success
    assert abs(result.data["result"] - 66.6666) < 0.001


def test_expressao_invalida_nao_executa_codigo():
    # Garante que não é um eval() cru: uma chamada de função não é aceita.
    result = calculate(expression="__import__('os').system('echo hackeado')")
    assert result.success is False


def test_expressao_vazia_nao_quebra():
    result = calculate(expression="")
    assert result.success is False
