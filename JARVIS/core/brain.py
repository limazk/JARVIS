"""
Abstração de LLM (o "cérebro" do Jarvis) — seção 4 do spec.

O resto do sistema nunca fala diretamente com a API da Anthropic,
OpenAI, etc. Ele conversa com um `LLMProvider`. Isso permite trocar
de provedor apenas mudando LLM_PROVIDER no .env, sem tocar no
router nem no agent.

Cada provider expõe o mesmo contrato:
    decide(system_prompt, messages, tools) -> LLMDecision

Uma LLMDecision é OU uma resposta em texto (conversa normal) OU um
pedido para chamar uma ferramenta (tool_name + tool_input) — nunca
as duas coisas. O texto do LLM nunca afirma que uma ação já
aconteceu; quem confirma isso é o router, depois do retorno real
da tool (tools/base.py).
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from config.settings import settings
from core.performance import current_trace

logger = logging.getLogger("jarvis.brain")


@dataclass
class LLMDecision:
    kind: str  # "text" ou "tool_call"
    text: Optional[str] = None
    tool_name: Optional[str] = None
    tool_input: dict = field(default_factory=dict)
    retryable_error: bool = False


class OllamaHealth(str, Enum):
    OFFLINE = "OLLAMA_OFFLINE"
    ONLINE = "OLLAMA_ONLINE"
    MODEL_MISSING = "MODEL_MISSING"
    MODEL_READY = "MODEL_READY"
    MODEL_ERROR = "MODEL_ERROR"


class LLMProvider(ABC):
    """Interface que todo provedor de LLM precisa implementar."""

    @abstractmethod
    def decide(self, system_prompt: str, messages: list[dict], tools: list[dict]) -> LLMDecision:
        """Envia a conversa + ferramentas disponíveis e devolve a decisão do modelo."""
        raise NotImplementedError

    @property
    @abstractmethod
    def available(self) -> bool:
        """True se o provider está configurado (ex.: tem API key)."""
        raise NotImplementedError


class ClaudeProvider(LLMProvider):
    def __init__(self) -> None:
        self._client = None
        if settings.anthropic_api_key:
            try:
                import anthropic

                self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            except ImportError:
                logger.warning("Pacote 'anthropic' não instalado (pip install anthropic).")

    @property
    def available(self) -> bool:
        return self._client is not None

    def decide(self, system_prompt: str, messages: list[dict], tools: list[dict]) -> LLMDecision:
        if not self._client:
            return LLMDecision(kind="text", text="Meu cérebro de IA não está configurado no momento.")

        started = time.perf_counter()
        response = self._client.messages.create(
            model=settings.claude_model,
            max_tokens=1024,
            system=system_prompt,
            messages=messages or [{"role": "user", "content": "Olá"}],
            tools=tools if tools else None,
        )
        trace = current_trace()
        if trace is not None and "llm_first_token" not in trace.metrics:
            trace.set("llm_first_token", time.perf_counter() - started)

        tool_block = next((b for b in response.content if b.type == "tool_use"), None)
        if tool_block is not None:
            return LLMDecision(kind="tool_call", tool_name=tool_block.name, tool_input=dict(tool_block.input))

        text_block = next((b for b in response.content if b.type == "text"), None)
        return LLMDecision(kind="text", text=text_block.text if text_block else "")


class _OpenAICompatibleProvider(LLMProvider):
    """
    Base para qualquer provedor que fale o mesmo protocolo de chat da
    OpenAI (chat completions + function calling via o SDK `openai`) —
    isso inclui a própria OpenAI, mas também Google Gemini e Groq, que
    expõem um endpoint "compatível com OpenAI" e por isso não precisam
    de nenhum SDK próprio. Evita repetir a mesma lógica de tool-calling
    três vezes; cada subclasse só define a chave, o modelo e (quando
    não for a OpenAI de verdade) a `base_url` do provedor.
    """

    display_name = "LLM"

    def __init__(self, api_key: str, model: str, base_url: Optional[str] = None) -> None:
        self._model = model
        self._client = None
        if api_key:
            try:
                import openai

                kwargs = {"api_key": api_key}
                if base_url:
                    kwargs["base_url"] = base_url
                self._client = openai.OpenAI(**kwargs)
            except ImportError:
                logger.warning("Pacote 'openai' não instalado (pip install openai).")

    @property
    def available(self) -> bool:
        return self._client is not None

    def decide(self, system_prompt: str, messages: list[dict], tools: list[dict]) -> LLMDecision:
        if not self._client:
            return LLMDecision(
                kind="text",
                text=f"Provedor {self.display_name} não configurado (falta a chave de API no .env).",
            )

        compat_tools = [
            {
                "type": "function",
                "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]},
            }
            for t in tools
        ]
        started = time.perf_counter()
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "system", "content": system_prompt}, *messages],
            tools=compat_tools or None,
        )
        trace = current_trace()
        if trace is not None and "llm_first_token" not in trace.metrics:
            trace.set("llm_first_token", time.perf_counter() - started)
        choice = response.choices[0].message
        if choice.tool_calls:
            import json

            call = choice.tool_calls[0]
            return LLMDecision(
                kind="tool_call",
                tool_name=call.function.name,
                tool_input=json.loads(call.function.arguments or "{}"),
            )
        return LLMDecision(kind="text", text=choice.content or "")


class OpenAIProvider(_OpenAICompatibleProvider):
    display_name = "OpenAI"

    def __init__(self) -> None:
        super().__init__(api_key=settings.openai_api_key, model=settings.openai_model)


class GeminiProvider(_OpenAICompatibleProvider):
    """
    Google Gemini — tem camada gratuita sem exigir cartão de crédito
    (limites generosos para uso pessoal; ver
    https://ai.google.dev/gemini-api/docs/rate-limits). Usa o endpoint
    de compatibilidade com a API da OpenAI que o próprio Gemini expõe,
    então não precisa de nenhuma biblioteca extra além do `openai`.

    Gere sua chave grátis em https://aistudio.google.com/apikey
    (não pede cartão) e coloque em GEMINI_API_KEY no .env.
    """

    display_name = "Gemini"

    def __init__(self) -> None:
        super().__init__(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )


class GroqProvider(_OpenAICompatibleProvider):
    """
    Groq — também tem camada gratuita sem cartão de crédito, rodando
    modelos abertos (Llama, Qwen, etc.) com inferência muito rápida.
    Mesmo esquema de compatibilidade com a API da OpenAI.

    Gere sua chave grátis em https://console.groq.com/keys (não pede
    cartão) e coloque em GROQ_API_KEY no .env.
    """

    display_name = "Groq"

    def __init__(self) -> None:
        super().__init__(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            base_url="https://api.groq.com/openai/v1",
        )


class LocalProvider(LLMProvider):
    """
    Modelos locais via Ollama (rodando em localhost, grátis, 100% offline).

    Usa o endpoint /api/chat do Ollama, que suporta tool-calling
    estruturado (formato compatível com OpenAI: "tools" na requisição,
    "tool_calls" na resposta) DESDE QUE o modelo escolhido suporte a
    funcionalidade — hoje isso inclui llama3.1, llama3.2, mistral-nemo,
    qwen2.5, entre outros. Modelos mais antigos/pequenos (ex.: llama3
    puro) podem ignorar as tools e só responder texto — nesse caso o
    Jarvis simplesmente trata a resposta como conversa, sem quebrar.

    Requer o Ollama instalado (https://ollama.com) e rodando, com o
    modelo já baixado (`ollama pull llama3.1`, por exemplo).
    """

    def __init__(self) -> None:
        self._url = settings.local_llm_url.rstrip("/")

    def server_status(self) -> tuple[OllamaHealth, str]:
        """Health do servidor, independente de o modelo pedido estar instalado."""
        try:
            import requests

            response = requests.get(f"{self._url}/api/tags", timeout=2)
        except Exception as exc:
            return OllamaHealth.OFFLINE, f"Ollama offline em {self._url}: {exc}"
        if not response.ok:
            return OllamaHealth.MODEL_ERROR, f"Ollama respondeu HTTP {response.status_code}."
        return OllamaHealth.ONLINE, "Servidor Ollama online."

    def health_check(self) -> tuple[OllamaHealth, str]:
        """Distingue servidor offline, modelo ausente e modelo pronto."""
        try:
            import requests

            response = requests.get(f"{self._url}/api/tags", timeout=2)
        except Exception as exc:
            return OllamaHealth.OFFLINE, f"Ollama offline em {self._url}: {exc}"
        if not response.ok:
            return OllamaHealth.MODEL_ERROR, f"Ollama respondeu HTTP {response.status_code}."
        try:
            models = response.json().get("models", [])
            names = {str(item.get("name", "")) for item in models}
            names.update(str(item.get("model", "")) for item in models)
        except (TypeError, ValueError, AttributeError) as exc:
            return OllamaHealth.MODEL_ERROR, f"Resposta inválida do Ollama: {exc}"
        wanted = settings.local_llm_model
        if wanted not in names and f"{wanted}:latest" not in names:
            return OllamaHealth.MODEL_MISSING, f"Modelo ausente. Execute: ollama pull {wanted}"
        return OllamaHealth.MODEL_READY, f"Ollama online; modelo {wanted} pronto."

    @property
    def available(self) -> bool:
        return self.health_check()[0] == OllamaHealth.MODEL_READY

    @staticmethod
    def _to_ollama_tools(tools: list[dict]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"],
                },
            }
            for t in tools
        ]

    def decide(self, system_prompt: str, messages: list[dict], tools: list[dict]) -> LLMDecision:
        try:
            import requests

            chat_messages = [{"role": "system", "content": system_prompt}, *messages]
            payload = {
                "model": settings.local_llm_model,
                "messages": chat_messages,
                "stream": False,
                # Evita que o Ollama descarregue o modelo da memória entre
                # mensagens (o padrão dele é 5min) — sem isso, cada resposta
                # depois de uma pausa paga o custo de recarregar o modelo do
                # disco, o que parece "o Jarvis está lento" mesmo com o
                # Ollama funcionando bem.
                "keep_alive": settings.ollama_keep_alive,
                "options": {
                    "num_ctx": settings.local_llm_context,
                    "temperature": settings.local_llm_temperature,
                },
                "think": settings.local_llm_thinking,
            }
            if tools:
                payload["tools"] = self._to_ollama_tools(tools)

            started = time.perf_counter()
            resp = requests.post(f"{self._url}/api/chat", json=payload, timeout=settings.local_llm_timeout)
            resp.raise_for_status()
            data = resp.json()
            trace = current_trace()
            if trace is not None and "llm_first_token" not in trace.metrics:
                # O endpoint atual não faz streaming; isto mede o primeiro byte
                # observável pelo cliente. O total do modelo vem logo abaixo.
                trace.set("llm_first_token", time.perf_counter() - started)
            if settings.debug:
                logger.debug(
                    "Ollama modelo=%s total=%.2fs carga=%.2fs",
                    settings.local_llm_model,
                    float(data.get("total_duration", 0)) / 1_000_000_000,
                    float(data.get("load_duration", 0)) / 1_000_000_000,
                )
            message = data.get("message", {})

            tool_calls = message.get("tool_calls") or []
            if tool_calls:
                call = tool_calls[0]["function"]
                return LLMDecision(kind="tool_call", tool_name=call.get("name"), tool_input=call.get("arguments") or {})

            return LLMDecision(kind="text", text=message.get("content", ""))
        except Exception as exc:
            return LLMDecision(
                kind="text",
                text=f"Modelo local indisponível ({exc}). Verifique se o Ollama está rodando (ollama serve).",
                retryable_error=True,
            )


_PROVIDER_CLASSES: dict[str, type] = {
    "claude": ClaudeProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
    "groq": GroqProvider,
    "local": LocalProvider,
}

# Ordem de fallback GRÁTIS, usada depois do provedor escolhido em
# LLM_PROVIDER (seção FallbackLLMProvider). Claude/OpenAI (pagos) nunca
# entram aqui sozinhos — só participam do fallback quando são o próprio
# LLM_PROVIDER escolhido, pra nunca trocar de um provedor pago pra outro
# provedor pago sem o usuário pedir isso explicitamente.
_FREE_FALLBACK_ORDER = ["gemini", "groq", "local"]


def get_llm_provider() -> LLMProvider:
    """Instancia exatamente o provedor escolhido em LLM_PROVIDER — sem fallback."""
    provider_cls = _PROVIDER_CLASSES.get(settings.llm_provider, ClaudeProvider)
    return provider_cls()


class FallbackLLMProvider(LLMProvider):
    """
    Provider "meta" que tenta o LLM_PROVIDER escolhido primeiro e, se ele
    falhar — erro de API (limite de requisições estourado, sem crédito,
    chave inválida, serviço fora do ar) ou simplesmente não estiver
    configurado —, cai automaticamente para o próximo da lista, sem
    precisar editar o .env nem reiniciar o Jarvis (era o item "fallback
    automático entre provedores, adiado pra versão 3.0" do roadmap).

    Ordem: o provedor escolhido em LLM_PROVIDER primeiro, depois os
    provedores GRÁTIS (Gemini -> Groq -> Ollama local), pulando os que
    não têm chave/instalação configurada. Ative/desative isso com
    LLM_AUTO_FALLBACK no .env (ligado por padrão).
    """

    def __init__(self, chain: Optional[list[tuple[str, LLMProvider]]] = None) -> None:
        if chain is not None:
            self._chain = chain
            return

        self._chain = []
        seen: set[str] = set()
        for name in (settings.llm_provider, *_FREE_FALLBACK_ORDER):
            if name in seen or name not in _PROVIDER_CLASSES:
                continue
            seen.add(name)
            self._chain.append((name, _PROVIDER_CLASSES[name]()))

    @property
    def available(self) -> bool:
        return any(provider.available for _, provider in self._chain)

    def decide(self, system_prompt: str, messages: list[dict], tools: list[dict]) -> LLMDecision:
        last_error: Optional[Exception] = None
        tried_any = False
        for name, provider in self._chain:
            if not provider.available:
                continue
            tried_any = True
            try:
                decision = provider.decide(system_prompt, messages, tools)
                if decision.retryable_error:
                    last_error = RuntimeError(decision.text or f"Falha no provedor {name}")
                    logger.warning("Provedor de IA '%s' falhou — tentando o próximo da lista.", name)
                    continue
                return decision
            except Exception as exc:  # nunca deixa um provedor derrubar o Jarvis inteiro
                logger.warning("Provedor de IA '%s' falhou (%s) — tentando o próximo da lista.", name, exc)
                last_error = exc
                continue

        if not tried_any:
            return LLMDecision(
                kind="text",
                text="Nenhum provedor de IA está configurado no momento (abra 'Configurar IA' na interface).",
            )
        return LLMDecision(
            kind="text",
            text=f"Todos os provedores de IA configurados falharam agora ({last_error}). Tente de novo em instantes.",
        )


def build_llm_provider() -> LLMProvider:
    """
    Ponto de entrada usado pelo agente (core/agent.py): devolve o
    FallbackLLMProvider (LLM_PROVIDER + fallback automático pros
    gratuitos) quando LLM_AUTO_FALLBACK=true (padrão), ou só o provedor
    escolhido sozinho, sem fallback, quando estiver desligado.
    """
    if settings.llm_auto_fallback:
        return FallbackLLMProvider()
    return get_llm_provider()
