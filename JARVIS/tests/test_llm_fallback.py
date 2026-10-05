"""
Testes do fallback automático entre provedores de IA
(core/brain.py::FallbackLLMProvider) — item do roadmap implementado
nesta rodada ("fallback automático, adiado pra versão 3.0").
"""
from __future__ import annotations

from config.settings import settings
from core.brain import ClaudeProvider, FallbackLLMProvider, LLMDecision, LLMProvider, build_llm_provider


class _FakeProvider(LLMProvider):
    def __init__(self, available: bool = True, raises: Exception | None = None, text: str = "ok") -> None:
        self._available = available
        self._raises = raises
        self._text = text
        self.called = False

    @property
    def available(self) -> bool:
        return self._available

    def decide(self, system_prompt, messages, tools) -> LLMDecision:
        self.called = True
        if self._raises:
            raise self._raises
        return LLMDecision(kind="text", text=self._text)


def test_usa_o_primeiro_disponivel_da_cadeia():
    a = _FakeProvider(available=False)
    b = _FakeProvider(available=True, text="resposta do b")
    provider = FallbackLLMProvider(chain=[("a", a), ("b", b)])

    decision = provider.decide("sys", [], [])

    assert decision.text == "resposta do b"
    assert not a.called
    assert b.called


def test_cai_pro_proximo_quando_o_primeiro_falha_com_excecao():
    a = _FakeProvider(available=True, raises=RuntimeError("limite estourado"))
    b = _FakeProvider(available=True, text="resposta do b")
    provider = FallbackLLMProvider(chain=[("a", a), ("b", b)])

    decision = provider.decide("sys", [], [])

    assert decision.text == "resposta do b"
    assert a.called and b.called


def test_nenhum_disponivel_retorna_mensagem_honesta():
    a = _FakeProvider(available=False)
    provider = FallbackLLMProvider(chain=[("a", a)])

    decision = provider.decide("sys", [], [])

    assert "nenhum provedor" in decision.text.lower()


def test_todos_falham_retorna_mensagem_honesta_com_o_ultimo_erro():
    a = _FakeProvider(available=True, raises=RuntimeError("erro a"))
    b = _FakeProvider(available=True, raises=RuntimeError("erro b"))
    provider = FallbackLLMProvider(chain=[("a", a), ("b", b)])

    decision = provider.decide("sys", [], [])

    assert "falharam" in decision.text.lower()
    assert "erro b" in decision.text


def test_available_e_true_se_qualquer_um_da_cadeia_estiver_disponivel():
    a = _FakeProvider(available=False)
    b = _FakeProvider(available=True)
    provider = FallbackLLMProvider(chain=[("a", a), ("b", b)])
    assert provider.available is True


def test_available_e_false_se_ninguem_da_cadeia_estiver_disponivel():
    a = _FakeProvider(available=False)
    provider = FallbackLLMProvider(chain=[("a", a)])
    assert provider.available is False


def test_build_llm_provider_usa_fallback_quando_ligado(monkeypatch):
    monkeypatch.setattr(settings, "llm_auto_fallback", True)
    provider = build_llm_provider()
    assert isinstance(provider, FallbackLLMProvider)


def test_build_llm_provider_usa_provedor_unico_quando_desligado(monkeypatch):
    monkeypatch.setattr(settings, "llm_auto_fallback", False)
    monkeypatch.setattr(settings, "llm_provider", "claude")

    provider = build_llm_provider()

    assert isinstance(provider, ClaudeProvider)
    assert not isinstance(provider, FallbackLLMProvider)


def test_cadeia_automatica_comeca_pelo_provedor_escolhido(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "groq")
    provider = FallbackLLMProvider()
    names = [name for name, _ in provider._chain]
    assert names == ["groq", "gemini", "local"]  # não duplica "groq"


def test_cadeia_automatica_com_provedor_pago_desce_pros_gratuitos(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "claude")
    provider = FallbackLLMProvider()
    names = [name for name, _ in provider._chain]
    assert names == ["claude", "gemini", "groq", "local"]
