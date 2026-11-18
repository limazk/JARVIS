# JARVIS — Claude Max em múltiplas abas

Área Claude no painel pywebview, preservando o tema escuro/roxo.
Cada aba possui uma sessão independente do Claude Code, seleção de modelo
(padrão, Sonnet ou Opus), renomeação e histórico local persistido em SQLite.

## Como usar no Kali Linux

1. Instale uma versão atual do Claude Code CLI seguindo a documentação oficial.
2. No terminal, execute: claude auth login
3. Entre com sua conta da assinatura Max, não com a conta da Console/API.
4. Verifique com: claude auth status
   O campo authMethod deve indicar claude.ai.
5. Na pasta local do JARVIS, abra a interface:
   cd ~/JARVIS/JARVIS
   python main.py
6. Na barra lateral, abra Claude e clique em + Nova aba.
7. Escolha a opção de modelo antes de criar cada aba, envie mensagens e alterne
   entre sessões. A aba preserva o contexto pela opção --resume.

## Telemetria e cancelamento (branch de melhoria)

- Cada resposta bem-sucedida registra em `claude_tab_usage` os contadores de
  tokens informados pelo JSON do Claude Code CLI, quando presentes.
- São mostrados os totais desta aba, do dia (UTC), dos últimos 7 dias e de
  todo o histórico registrado localmente.
- A tela separa entrada, saída, leitura de cache e criação de cache; não
  duplica `usage` e `modelUsage` na mesma chamada.
- Chamadas anteriores à atualização e respostas do CLI sem `usage` /
  `modelUsage` **não são estimadas**. Os números podem ser incompletos.
- **Cota diária/semanal restante do Claude Max: indisponível.** O consumo
  observado em tokens não equivale ao limite comercial da assinatura; a
  interface não inventa porcentagem ou tempo restante. Nem as métricas
  indicam cobrança extra na API.
- O botão **Cancelar** envia término ao processo desta aba. As outras abas
  continuam independentes. O encerramento pode levar alguns instantes.
- O uso fica no mesmo SQLite local não criptografado. A exclusão de uma aba
  também remove suas métricas locais, mas não apaga sessões próprias do CLI.
- Ainda não há streaming de respostas nem execução de ferramentas nesta
  interface. Continuam necessários testes reais com Claude Max e pywebview.

## Limitações e segurança

- Usa Claude Code CLI (claude -p --output-format json), não incorpora o
  site claude.ai, nem sincroniza as conversas do navegador.
- É uma interface de conversa sem ferramentas: flags --bare, --tools vazio,
  --disallowedTools mcp__* e --max-turns 1.
- Remove do subprocesso a chave ANTHROPIC_API_KEY e as variáveis de
  autenticação da Console. A assinatura Max precisa estar autenticada no CLI.
- Não ativa recarga da API, mas a assinatura tem seus próprios limites
  compartilhados de uso. Não há promessas de uso ilimitado.
- O histórico fica salvo no arquivo local database/claude_tabs.sqlite3,
  que está ignorado pelo Git. Não existe criptografia de conteúdo neste banco.
  Não use as abas para digitar credenciais.
- O Claude Code também mantém arquivos de sessão em seu diretório próprio;
  excluir uma aba do JARVIS não apaga automaticamente os arquivos dele.
- Até 12 abas, com uma solicitação por aba em execução de cada vez.
- Cada chamada pode levar até 240 segundos. A saída é apresentada ao final
  da chamada, sem streaming de tokens.
- Requer versão do Claude Code que entenda os flags citados. Se uma aba
  falhar por incompatibilidade, atualize o Claude Code.
- Instalação, login, reprodução pywebview e uso real ainda necessitam
  homologação na máquina do usuário.

## Testes

Execute na subpasta JARVIS/ do repositório:

    python -m pytest -q tests/test_claude_tabs.py

Os testes usam CLI falso e não consomem tokens do Max. Incluem persistência,
telemetria, valores malformados e cancelamento de processos. Não substituem
homologação visual e autenticação reais.

## Escopo e isolamento

Implementação apenas em interface_web/, testes e docs.
Não altera o NEXUS, o shell, a voz, nem a branch de segurança do PR #5.
Nenhum merge ou deploy automático.
