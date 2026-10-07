# NEXUS v0.3 — Orquestrador econômico integrado ao JARVIS

O NEXUS vive dentro do JARVIS e foi desenhado para gastar computação local à vontade, mas evitar chamadas/tokens online desnecessários.

## Fluxo

```text
TAREFA
  ↓
REGRAS LOCAIS (0 tokens)
  ↓
confiança suficiente?
  ├─ sim → executa diretamente
  └─ não → ROUTER ONLINE CURTO
              ↓
        Gemini → Groq → OpenRouter → Mistral → Cloudflare → Together → Cerebras
              ↓
        2ª IA apenas se a primeira falhar ou estiver pouco confiante
              ↓
        escolhe UM worker
              ↓
        execução
              ↓
        validação local
```

## Providers disponíveis

### Terminal / execução real no repositório
- Codex CLI
- Claude CLI
- Gemini CLI
- Ollama local
- JARVIS interno

### APIs online
- Gemini API
- Groq
- OpenRouter
- Mistral
- Cloudflare Workers AI
- Together AI
- Cerebras

As APIs online são usadas principalmente para roteamento, planejamento, classificação, revisão e respostas. Para tarefas que precisam editar/testar arquivos de verdade, o NEXUS prioriza Codex/Claude/Gemini CLI/JARVIS.

## Economia de tokens

Por padrão:

- intenções conhecidas do JARVIS nunca usam router online;
- tarefas locais com confiança >= 85% não usam router online;
- o router recebe no máximo 1600 caracteres da tarefa;
- a resposta do router é limitada a 96 tokens;
- no máximo 3 tentativas de router, e só em falha/baixa confiança;
- decisões online ficam em cache por 30 minutos;
- somente um worker é chamado por padrão;
- não existe votação entre vários modelos para toda tarefa;
- o worker recebe apenas memória relevante e contexto compacto;
- saída de API do worker é limitada por padrão a 1200 tokens.

## Cadeia padrão do router

```text
Gemini
  ↓ falha/baixa confiança
Groq GPT-OSS 20B
  ↓ falha/baixa confiança
OpenRouter Free
  ↓
Mistral
  ↓
Cloudflare Workers AI
  ↓
Together AI
  ↓
Cerebras
```

A cadeia pode ser alterada em `.env`:

```env
NEXUS_ROUTER_CHAIN=gemini,groq,openrouter,mistral,cloudflare,together,cerebras
```

## Configuração principal

```env
NEXUS_ONLINE_ROUTER=true
NEXUS_ROUTER_VERIFY_ALWAYS=false
NEXUS_ROUTER_CONFIDENCE=0.85
NEXUS_ROUTER_MAX_INPUT_CHARS=1600
NEXUS_ROUTER_MAX_OUTPUT_TOKENS=96
NEXUS_ROUTER_MAX_CALLS=3
NEXUS_ROUTER_CACHE_TTL=1800
NEXUS_WORKER_MAX_OUTPUT_TOKENS=1200
```

Se quiser que TODA tarefa não-local seja verificada por uma IA online:

```env
NEXUS_ROUTER_VERIFY_ALWAYS=true
```

Isso aumenta o consumo de tokens e por isso fica desligado por padrão.

## Chaves opcionais

Configure apenas os providers que quiser usar:

```env
GEMINI_API_KEY=
GROQ_API_KEY=
OPENROUTER_API_KEY=
MISTRAL_API_KEY=
CLOUDFLARE_ACCOUNT_ID=
CLOUDFLARE_API_TOKEN=
TOGETHER_API_KEY=
CEREBRAS_API_KEY=
```

Nenhuma chave deve ser commitada.

## Modelos padrão do NEXUS

```env
NEXUS_GEMINI_MODEL=gemini-3.8-flash
NEXUS_GROQ_MODEL=openai/gpt-oss-20b
OPENROUTER_MODEL=openrouter/free
MISTRAL_MODEL=ministral-3b-latest
CLOUDFLARE_MODEL=@cf/openai/gpt-oss-20b
TOGETHER_MODEL=Prism-ML/Ternary-Bonsai-27B
CEREBRAS_MODEL=zai-glm-4.7
```

Todos podem ser trocados pelo `.env` sem editar código.

## Integração com JARVIS

O NEXUS reutiliza:

- `JarvisAgent`;
- ToolRegistry;
- memória de longo prazo;
- ROTINA;
- PermissionManager;
- banco SQLite;
- logs/atividade.

Se um provider externo falhar, o NEXUS volta para o JARVIS sem sair chamando vários modelos em sequência para executar a tarefa.

## Como abrir

```bash
cd JARVIS
python main.py --nexus
```

ou:

```bash
python -m nexus
```

Para criar o comando global:

```bash
chmod +x scripts/install_nexus_cli.sh
./scripts/install_nexus_cli.sh
nexus
```

## Comandos da TUI

```text
/providers   mostra todos os providers e se estão configurados
/tokens      mostra tokens/chamadas rastreados da última tarefa
/refresh     reescaneia CLIs e chaves
/demo        testa o pipeline sem chamar IA
/result      alterna logs/resultado
/clear       limpa a tela
/quit        fecha o NEXUS
```

## Observação sobre métricas

O NEXUS rastreia tokens devolvidos pelas APIs online compatíveis. CLIs como Codex/Claude podem ter contabilização própria e o uso interno de LLM do JARVIS não é somado automaticamente ao contador do NEXUS.
