# NEXUS — Orquestrador integrado ao JARVIS

O NEXUS agora vive dentro do projeto JARVIS e reutiliza o núcleo real do assistente.

## O que está integrado

- `JarvisAgent` como executor interno e fallback.
- `ToolRegistry` completo do JARVIS, incluindo ROTINA, arquivos, sistema, GitHub, Gmail, Calendar e demais tools já registradas.
- memória de longo prazo do JARVIS para contexto relevante.
- mesmo banco SQLite do JARVIS, com a tabela `nexus_jobs` para histórico.
- mesmo sistema de permissões: ações MEDIUM/HIGH abrem confirmação dentro da TUI.
- workers opcionais: Codex CLI, Claude CLI, Gemini CLI e Ollama.
- fallback automático para o JARVIS se um worker externo não existir ou falhar.

## Como abrir

Dentro da pasta `JARVIS/`:

```bash
python main.py --nexus
```

Também funciona:

```bash
python -m nexus
```

Para instalar um comando global no Linux:

```bash
chmod +x scripts/install_nexus_cli.sh
./scripts/install_nexus_cli.sh
nexus
```

## Roteamento

O NEXUS primeiro verifica o parser local do próprio JARVIS. Se a mensagem já corresponde a uma tool local, ela permanece no JARVIS.

Depois:

- código: Codex → Claude → Gemini → Ollama → JARVIS
- revisão: Claude → Codex → Gemini → Ollama → JARVIS
- pesquisa: Gemini → Claude → JARVIS → Ollama → Codex
- geral: JARVIS → Claude → Gemini → Ollama → Codex

## Comandos da TUI

```text
/providers
/refresh
/demo
/result
/clear
/quit
```

## Segurança

Workers externos não recebem chaves do JARVIS pelo NEXUS. Eles usam a autenticação dos próprios CLIs instalados no computador.

Ações executadas pelo `JarvisAgent` continuam passando pelo `PermissionManager`. Quando uma ação exige confirmação, a TUI mostra um modal `[S] Sim / [N] Não`.

## Variáveis opcionais

```bash
NEXUS_PROVIDER_TIMEOUT=300
NEXUS_MAX_OUTPUT=50000
```

O modelo do Ollama é o mesmo configurado em `LOCAL_LLM_MODEL`.
