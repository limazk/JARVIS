# NEXUS v0.4 — Dual Router + Workers

O NEXUS usa somente **Grok** e **Mistral** para identificar/rotear tarefas.
Todas as outras IAs ficam disponíveis como **workers funcionais**, no mesmo
conceito de Claude/Codex: são escolhidas para executar a tarefa adequada.

## Arquitetura

```text
TAREFA
  ↓
REGRAS LOCAIS (0 tokens)
  ↓
a rota já é óbvia?
  ├─ sim → escolhe worker
  └─ não
       ↓
     GROK
       ↓ se falhar/baixa confiança
     MISTRAL
       ↓
     decisão de rota
       ↓
  ┌────┴──────────────────────────────────────────────────────┐
  │                    WORKERS / FUNCIONALIDADES              │
  │                                                          │
  │ Codex · Claude · Gemini CLI · Ollama · JARVIS            │
  │ Gemini API · Groq · OpenRouter · Cloudflare              │
  │ Together AI · Cerebras                                   │
  └──────────────────────────────────────────────────────────┘
       ↓
  um worker por padrão
       ↓
  validação local
       ↓
  entrega
```

## Papéis

### Identificadores — não executam a tarefa final

- **Grok / xAI**
- **Mistral**

Eles recebem apenas um prompt curto dizendo a tarefa, a decisão local e os
workers disponíveis. A resposta deve ser um JSON pequeno com rota, tipo,
confiança e motivo.

O NEXUS bloqueia Grok/Mistral no executor: mesmo que uma resposta tente
escolher um deles como worker, eles não são usados para execução final.

### Workers / funcionalidades

- Codex CLI
- Claude CLI
- Gemini CLI
- Ollama
- JARVIS interno
- Gemini API
- Groq
- OpenRouter
- Cloudflare Workers AI
- Together AI
- Cerebras

CLIs e JARVIS podem ter acesso local ao projeto/tools conforme a integração.
APIs online são workers de análise, raciocínio, revisão, pesquisa e respostas;
elas não devem fingir que editaram arquivos se não têm acesso ao terminal.

## Economia de tokens

Por padrão:

- comandos conhecidos do JARVIS: 0 tokens de router;
- regras locais com confiança >= 85%: 0 tokens de router;
- quando ambíguo: Grok tenta primeiro;
- Mistral só entra se Grok falhar ou devolver baixa confiança;
- no máximo 2 chamadas de identificação;
- entrada do identificador limitada a 1600 caracteres;
- saída limitada a 96 tokens;
- decisão fica em cache por 30 minutos;
- somente um worker é chamado por padrão;
- o contexto do worker contém apenas memória relevante/compacta.

## Configuração

```env
NEXUS_ONLINE_ROUTER=true
NEXUS_ROUTER_VERIFY_ALWAYS=false
NEXUS_ROUTER_CONFIDENCE=0.85
NEXUS_ROUTER_CHAIN=grok,mistral
NEXUS_ROUTER_MAX_INPUT_CHARS=1600
NEXUS_ROUTER_MAX_OUTPUT_TOKENS=96
NEXUS_ROUTER_MAX_CALLS=2
NEXUS_ROUTER_CACHE_TTL=1800
```

### Grok / xAI — identificador 1

```env
XAI_API_KEY=
NEXUS_GROK_MODEL=grok-4.7
```

### Mistral — identificador 2

```env
MISTRAL_API_KEY=
MISTRAL_MODEL=ministral-3b-latest
```

## Workers opcionais

Configure apenas os que quiser utilizar:

```env
GEMINI_API_KEY=
NEXUS_GEMINI_MODEL=gemini-3.8-flash

GROQ_API_KEY=
NEXUS_GROQ_MODEL=openai/gpt-oss-20b

OPENROUTER_API_KEY=
OPENROUTER_MODEL=openrouter/free

CLOUDFLARE_ACCOUNT_ID=
CLOUDFLARE_API_TOKEN=
CLOUDFLARE_MODEL=@cf/openai/gpt-oss-20b

TOGETHER_API_KEY=
TOGETHER_MODEL=Prism-ML/Ternary-Bonsai-27B

CEREBRAS_API_KEY=
CEREBRAS_MODEL=zai-glm-4.7
```

Codex, Claude e Gemini CLI são detectados pelo executável instalado no PATH.
Ollama é detectado localmente.

## Roteamento funcional

Exemplos:

```text
"corrija os testes desse backend"
  → regra local reconhece CODE com confiança alta
  → Codex
  → 0 chamada Grok/Mistral

"quero melhorar isso"
  → confiança local baixa
  → Grok identifica a necessidade
  → escolhe um worker
  → Mistral só verifica se necessário

"quanto ganhei essa semana?"
  → intent local do JARVIS
  → JARVIS/ROTINA
  → 0 chamada Grok/Mistral
```

Grok e Mistral nunca aparecem nas prioridades de execução final.

## TUI

`/providers` diferencia:

```text
Grok           IDENTIFICADOR · api
Mistral Router IDENTIFICADOR · api
Codex          WORKER · cli
Claude         WORKER · cli
Gemini         WORKER · api
Groq           WORKER · api
...
```

Comandos:

```text
/providers
/tokens
/refresh
/demo
/result
/clear
/quit
```

## Execução

```bash
cd JARVIS
python main.py --nexus
```

ou:

```bash
python -m nexus
```

## Segurança

- chaves ficam somente no `.env`;
- Grok/Mistral recebem contexto mínimo;
- o NEXUS não envia automaticamente o histórico inteiro;
- ações executadas pelo JARVIS continuam passando pelo PermissionManager;
- falha de worker cai para JARVIS em vez de disparar vários executores em cadeia.
