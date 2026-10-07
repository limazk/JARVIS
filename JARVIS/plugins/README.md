# Plugins do JARVIS/NEXUS

A camada de plugins fica entre os agentes/LLMs e serviços externos.

Fluxo:

    usuário -> NEXUS/JARVIS -> PluginRegistry -> PermissionManager -> plugin -> serviço

Credenciais nunca são colocadas no prompt do modelo. O modelo vê apenas nomes,
descrições, schemas e os resultados devolvidos pelo plugin.

## Núcleo

- plugins/base.py: contratos Plugin, PluginCapability, PluginStatus e PluginResult.
- plugins/registry.py: descoberta, catálogo e execução com permissões.
- plugins/bridge.py: transforma o PluginRegistry em Tools do JARVIS.
- plugins/broker.py: protocolo NEXUS_PLUGIN para workers externos pedirem uma ação sem receber segredo.
- plugins/mcp.py: cliente Streamable HTTP genérico para servidores MCP.
- plugins/builtin/: adapters nativos.

## Plugins registrados

### Desenvolvimento

- github: usa as Tools GitHub já existentes.
- filesystem: usa as Tools locais de arquivos.
- shell: usa o executor protegido do JARVIS.
- docker: containers.list, images.list, logs.
- supabase: projects.list, migrations.list, functions.list via CLI.
- render: services.list, deploys.list via API.
- vercel: deployments.list, deployment.inspect via CLI.

### Produtividade

- trello: boards.list, cards.list, card.create, card.move.
- notion: search, page.get, page.create, page.append.
- gmail: unread.list, send.
- calendar: events.list, event.create.
- drive: files.search.
- slack: channels.list, message.send.
- gitbook: bridge MCP configurável.

### Web

- browser: open, search.
- tavily: search.
- exa: search.

### Design / negócio / observabilidade

- figma: file.get, comments.list.
- stripe: customers.list, payments.list.
- posthog: bridge MCP configurável.
- datadog: bridge MCP configurável.

## Ferramentas expostas ao JARVIS

A inicialização padrão registra automaticamente:

- list_plugins
- plugin_status
- plugin_execute

Exemplo conceitual:

    plugin_execute(
        plugin="notion",
        action="search",
        arguments={"query": "EULER"}
    )

O nível de risco vem da capability. Leitura é LOW. Escritas como criar página,
card ou enviar mensagem são MEDIUM e passam pelo PermissionManager.

## MCP

Para um serviço que exponha MCP Streamable HTTP:

    GITBOOK_MCP_URL=
    GITBOOK_MCP_TOKEN=
    POSTHOG_MCP_URL=
    POSTHOG_MCP_TOKEN=
    DATADOG_MCP_URL=
    DATADOG_MCP_TOKEN=

Cada bridge MCP publica actions genéricas tools.list e tool.call.

## Configuração

Use apenas os plugins necessários. Todos ficam offline quando a credencial,
CLI ou URL obrigatória não estiver configurada.

Notion:

    NOTION_API_KEY=
    NOTION_API_VERSION=2022-06-28

Trello:

    TRELLO_API_KEY=
    TRELLO_TOKEN=

Render:

    RENDER_API_KEY=

Slack:

    SLACK_BOT_TOKEN=

Figma:

    FIGMA_API_TOKEN=

Stripe:

    STRIPE_SECRET_KEY=

Web:

    TAVILY_API_KEY=
    EXA_API_KEY=

Docker, Supabase e Vercel são detectados pelo executável no PATH.

## Segurança

- segredos ficam em variáveis de ambiente;
- respostas não incluem tokens de autenticação;
- operações de escrita passam por confirmação;
- plugins indisponíveis falham fechados;
- o JARVIS continua sendo a única camada que autoriza ações reais;
- um plugin não pode executar uma capability que não declarou.
