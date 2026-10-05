# JARVIS — assistente pessoal (protótipo)

Assistente pessoal multiplataforma para Kali Linux e Windows 10/11, inspirado no conceito do Jarvis. Não é
um chatbot: recebe comandos por voz ou texto, interpreta a intenção, executa
ferramentas reais no computador, consulta informações e mantém memória entre
conversas.

Escrito em Python, 100% modular, feito para rodar de dentro do VS Code.

## Funcionalidades

- **Texto, voz e Discord**: `python main.py --text`, `python main.py --voice`
  ou `python main.py --discord` (conversa por DM, de fora do PC).
- **Tool calling real**: o Jarvis só diz que fez algo depois que a ferramenta
  correspondente confirma sucesso — nunca inventa uma ação.
- **Modo sem IA**: comandos simples (`que horas são`, `abre o Chrome`, `volume
  30`, `calcula 15% de 1200`) são resolvidos por um parser local, sem chamar
  nenhuma API — mais rápido, grátis e funciona offline.
- **Cérebro trocável**: Qwen3.5 9B local via Ollama (padrão), Claude, OpenAI, Gemini ou Groq (esses dois
  últimos com camada gratuita sem cartão de crédito) ou um modelo local via
  Ollama (100% grátis e offline), todos por trás da mesma interface
  (`LLMProvider`).
- **Fallback automático entre provedores**: se o `LLM_PROVIDER` escolhido
  falhar (limite estourado, sem crédito, fora do ar) ou não estiver
  configurado, o Jarvis cai sozinho pros gratuitos (Gemini → Groq → Ollama
  local), sem precisar editar o `.env` nem reiniciar. Nunca troca sozinho
  entre dois provedores pagos — só desce pros gratuitos. Liga/desliga com
  `LLM_AUTO_FALLBACK` no `.env`.
- **Ferramentas**: abrir programas e sites, buscar na internet, previsão do
  tempo, sistema (CPU/RAM/disco/bateria/volume/bloqueio de tela), arquivos e
  pastas, área de transferência, print de tela, notas, lembretes (com
  verificação em segundo plano), timer, terminal (classificado por risco), git,
  GitHub, controle de reprodução do Spotify (tocar/pausar/pular/volume) e
  Gmail/Google Calendar/Google Drive (ler e-mail, mandar e-mail, ver/criar
  compromisso, buscar arquivo).
- **Memória**: curto prazo (contexto da conversa atual) e longo prazo em
  SQLite (`lembra que meu editor é o VS Code` → depois `abre meu editor`
  funciona).
- **Briefing matinal** (diga "bom dia", ou "me dá um resumo da manhã"):
  monta e fala um resumo juntando o que já foi guardado na memória desde
  ontem, previsão do tempo de hoje, agenda do dia (Google Calendar),
  e-mails não lidos (Gmail) e lembretes pendentes — tudo numa orquestração
  local das ferramentas que o Jarvis já tem (sem chamada extra de LLM, sem
  latência a mais). Cada seção só aparece se tiver um dado real: se o
  Google não estiver configurado, ou alguma consulta falhar, aquela seção
  simplesmente não entra no resumo — nunca é inventada. Ver `tools/briefing.py`.
- **Segurança**: todo comando passa por um `PermissionManager` — ações de
  risco pedem confirmação, e uma lista de comandos verdadeiramente perigosos
  (formatar disco, apagar tudo recursivamente, etc.) é bloqueada, ponto final.
- **Interface gráfica**: uma janela nativa (via `pywebview`) mostrando uma
  página HTML/CSS/JS local com tema escuro/roxo (paleta da logo oficial) —
  orbe central com brilho de verdade (glow/gradiente, não dá pra fazer isso
  em Tkinter), gráficos de histórico de CPU/RAM/disco, e uma barra lateral
  trocando entre duas páginas: "Visão geral" (CPU/RAM/disco, o orbe que
  reage ao estado do agente, status real de cada módulo — IA ativa, voz,
  memória, Spotify/Discord/GitHub/Google — e os interruptores de automação)
  e "Conversa" (o chat de texto/voz em si). Sem `pywebview` instalado (ou
  faltando o WebView2 Runtime no Windows), cai sozinho pra uma versão
  alternativa em CustomTkinter (mesmas duas páginas, visual mais simples) —
  ver "Interface gráfica não abre" na solução de problemas.

## Arquitetura

```
jarvis/
├── main.py                # ponto de entrada (--text / --voice / --background / GUI / --doctor)
├── core/                  # agente, roteador, LLM, intenção, permissões, memória curta
├── voice/                 # microfone, STT, TTS, player interrompível, wake word
├── tools/                 # cada ferramenta que o Jarvis pode executar
├── memory/                # SQLite: conversas, memórias, notas, lembretes, atividades
├── config/                # settings.py (.env) e apps.json
├── platform_services/     # operações Linux/Windows escolhidas em runtime
├── personality/           # identidade e estilo, separados das permissões
├── integrations/          # clientes centralizados (incluindo ROTINA)
├── deploy/linux/          # modelo da unidade systemd --user
├── scripts/               # setup, diagnóstico e instalação do serviço Linux
├── interface_web/          # interface gráfica principal (janela pywebview + página web)
│   └── web/                # HTML/CSS/JS da interface (index.html, style.css, app.js)
├── interface/              # interface gráfica de reserva (CustomTkinter) + peças
│                           # compartilhadas com a interface_web (status_info.py)
├── database/               # jarvis.db (criado em runtime, não versionado)
├── logs/                   # jarvis.log (criado em runtime)
└── tests/                  # testes automatizados (pytest)
```

**Fluxo de uma mensagem:**

```
voz/texto → core/router.py
    1. core/intent.py tenta um padrão local (rápido, grátis, offline)
    2. se não bater, core/brain.py chama o LLM com tool-calling
    3. core/permissions.py decide se a ação pode rodar direto,
       precisa de confirmação, ou está bloqueada
    4. a tool executa e devolve {success, message, data}
    5. a resposta (nunca inventada) volta como texto + voz
```

## Requisitos

- Kali Linux/Debian ou Windows 10/11
- **Python 3.12** (recomendado — veja o aviso abaixo antes de usar uma versão
  mais nova)
- Microfone e caixa de som (opcional — só para o modo voz)
- Uma chave da API da Anthropic (opcional — sem ela, o Jarvis funciona só com
  comandos locais)

> **Por que Python 3.12 e não a versão mais nova?** O Jarvis usa algumas
> bibliotecas que dependem de código nativo pra funcionar no Windows
> (`pygame`/`pyaudio` pro áudio, `win11toast`→`winsdk` pras notificações,
> `pillow` pra print de tela). Essas bibliotecas só funcionam direto (sem
> precisar compilar nada na sua máquina) quando alguém já publicou um
> "instalador pronto" (wheel) pra sua versão exata do Python — e isso sempre
> demora meses depois de cada versão nova do Python sair. Numa versão muito
> nova (ex.: 3.13, 3.14), é bem provável que `pip install -r requirements.txt`
> comece a falhar tentando compilar pacote atrás de pacote com erros tipo
> `Building windows wheels requires Microsoft Visual Studio` ou
> `ModuleNotFoundError: No module named 'setuptools._distutils...'` — e pelo
> menos um desses pacotes (`winsdk`) simplesmente não tem instalador pronto
> pra nenhuma versão além da 3.12 ainda, então nem trocar a versão do pacote
> resolve, só usar um Python mais estabelecido mesmo. Python 3.12 tem
> cobertura completa hoje pra tudo que o Jarvis usa.
>
> Se você já tem uma versão mais nova instalada, não precisa desinstalar
> nada: instale o Python 3.12 também (em https://www.python.org/downloads/)
> e crie o venv apontando pra ele especificamente:
> ```bat
> py -3.12 -m venv .venv
> ```
> (em vez de `python -m venv .venv`) — o resto da instalação é igual.

## Instalação

```bat
git clone <seu-repositorio> jarvis
cd jarvis
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python main.py --text
```

## Configuração (.env)

Copie `.env.example` para `.env` e preencha o que quiser usar. Nunca coloque
chaves de API direto no código — o `.env` nunca deve ser commitado (já está no
`.gitignore`).

| Variável | Padrão | O que faz |
|---|---|---|
| `JARVIS_NAME` | `Jarvis` | Nome usado nas respostas |
| `LANGUAGE` | `pt-BR` | Idioma da voz/STT |
| `USER_TITLE` | `Senhor` | Como o Jarvis se dirige a você (ex.: "Sim, Senhor."). Deixe `USER_TITLE=` (vazio) para desligar |
| `DEBUG` | `false` | Mostra intenção/tool/parâmetros/tempo de cada comando |
| `VOICE_ENABLED` | `true` | Liga/desliga a fala de saída |
| `WAKE_WORD_ENABLED` | `false` | Ativa o modo "diga 'jarvis' antes do comando" |
| `WAKE_WORD` | `jarvis` | Palavra de ativação |
| `WAKE_WORD_MODEL` | `hey_jarvis` | Modelo acústico do openWakeWord; pode ser trocado sem reescrever o detector |
| `ALLOW_CRITICAL_ACTIONS` | `false` | Nunca ative sem entender os riscos (seção Segurança) |
| `LLM_PROVIDER` | `local` | `claude` \| `openai` \| `gemini` \| `groq` \| `local` |
| `ANTHROPIC_API_KEY` | — | Sua chave da Anthropic (pago por uso) |
| `CLAUDE_MODEL` | `claude-sonnet-4-5` | Modelo Claude usado |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | — | Só se `LLM_PROVIDER=openai` (pago por uso) |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | — / `gemini-3.6-flash` | Só se `LLM_PROVIDER=gemini` — **grátis, sem cartão** |
| `GROQ_API_KEY` / `GROQ_MODEL` | — / `openai/gpt-oss-120b` | Só se `LLM_PROVIDER=groq` — **grátis, sem cartão** |
| `LOCAL_LLM_URL` / `LOCAL_LLM_MODEL` | `http://127.0.0.1:11434` / `qwen3.5:9b` | Ollama local — **grátis, offline** |
| `LOCAL_LLM_CONTEXT` / `LOCAL_LLM_TEMPERATURE` | `8192` / `0.6` | Janela de contexto e temperatura do modelo local |
| `LOCAL_LLM_TIMEOUT` | `180` (segundos) | Tempo de espera pelo Ollama antes de desistir — aumente se sua máquina for lenta ou o modelo local for grande (ex.: `qwen2.5:14b`) |
| `OLLAMA_KEEP_ALIVE` | `15m` | Quanto tempo o Ollama mantém o modelo carregado entre mensagens — evita ter que recarregar o modelo do disco a cada pausa |
| `LLM_AUTO_FALLBACK` | `true` | Se `LLM_PROVIDER` falhar, cai sozinho pros gratuitos (Gemini→Groq→Ollama) |
| `STT_PROVIDER` | `google` | `google` (grátis, online) \| `whisper` (local) |
| `TTS_PROVIDER` | `edge` | `edge` (grátis) \| `pyttsx3` (offline) \| `elevenlabs` (pago) |
| `EDGE_TTS_VOICE` | `pt-BR-AntonioNeural` | Voz do Edge TTS |
| `ELEVENLABS_API_KEY` / `ELEVENLABS_VOICE_ID` | — | Só se `TTS_PROVIDER=elevenlabs` |
| `OPENWEATHER_API_KEY` | — | Não é necessária (o padrão usa wttr.in, grátis, sem key) |
| `WEATHER_CITY` | `Brasilia,BR` | Cidade padrão para clima |
| `GITHUB_TOKEN` | — | Personal access token (escopos `repo`, `read:user`) — habilita `list_my_repos`, `repo_info`, `create_issue` |
| `TESSERACT_CMD` | — | Caminho do `tesseract.exe`, só se o OCR não achar sozinho |
| `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` | — | App grátis em developer.spotify.com/dashboard — habilita tocar/pausar/pular/volume/ver música atual |
| `SPOTIFY_REDIRECT_URI` | `http://127.0.0.1:8888/callback` | Tem que ser IDÊNTICA à cadastrada no app do Spotify |
| `DISCORD_BOT_TOKEN` | — | Token do bot, gerado em discord.com/developers/applications — habilita `python main.py --discord` |
| `DISCORD_OWNER_ID` | — | Seu ID numérico do Discord — o bot ignora qualquer outra pessoa por segurança |

## Integrações (além das ferramentas locais)

- **GitHub API**: gere um token em GitHub → Settings → Developer settings →
  Personal access tokens (classic), escopos `repo` e `read:user`. Cole em
  `GITHUB_TOKEN`. Sem token, `git_status`/`git_push`/`open_github` continuam
  funcionando normalmente (não dependem de API).
- **Visão/OCR de tela** (`read_screen_text`, `read_image_text`): precisa do
  programa Tesseract OCR instalado à parte (não é só `pip install`) —
  https://github.com/UB-Mannheim/tesseract/wiki. Se o Jarvis não achar
  sozinho, defina `TESSERACT_CMD` no `.env`.
- **Modelo local com tool-calling** (`LLM_PROVIDER=local`, ou como fallback
  gratuito automático — veja `LLM_AUTO_FALLBACK`): instale o
  [Ollama](https://ollama.com), rode `ollama pull <modelo>` (baixe o mesmo
  nome que estiver em `LOCAL_LLM_MODEL` no `.env`) e deixe o `ollama serve`
  rodando. Modelos sem suporte a tool-calling ainda funcionam, só que apenas
  para conversa. Qual modelo escolher depende da sua placa de vídeo — como
  o Jarvis usa o Ollama sempre como um agente que chama ferramentas (abrir
  apps, Spotify, clima, etc.), e não pra bate-papo livre, um modelo pequeno
  *especializado em tool-calling* costuma acertar mais chamadas de função do
  que um modelo genérico maior do mesmo tamanho:
  - **Modelo desta fase**: `ollama pull qwen3.5:9b` (é o configurado no
    `.env.example`; o Ollama decide automaticamente entre CPU, GPU ou uso híbrido)
  - **12GB+ de VRAM**: dá pra usar um modelo mais moderno de uso geral, ex.
    `ollama pull gemma4:e4b-it-qat` (~6,1GB, multimodal, mais atualizado —
    ainda com suporte a tools, mas com uma taxa de erro em chamadas de
    função um pouco maior que o modelo especializado acima)
  - **Menos de 8GB de VRAM**: `ollama pull qwen2.5:7b` ou aceite rodar mais
    devagar com parte do modelo na CPU (`LOCAL_LLM_TIMEOUT` mais alto ajuda)
- **Gemini** (`LLM_PROVIDER=gemini`) e **Groq** (`LLM_PROVIDER=groq`): as duas
  únicas opções de nuvem com camada gratuita sem pedir cartão de crédito.
  Ambas expõem um endpoint compatível com a API da OpenAI, então o Jarvis usa
  o mesmo pacote `openai` já instalado para falar com elas — não precisa de
  nenhuma biblioteca extra. Gere a chave em
  https://aistudio.google.com/apikey (Gemini) ou
  https://console.groq.com/keys (Groq), cole em `GEMINI_API_KEY` ou
  `GROQ_API_KEY` no `.env`, e mude `LLM_PROVIDER`. Os limites gratuitos são
  generosos para uso pessoal, mas existem (poucos pedidos por minuto/dia) —
  se estourar, a resposta do provedor vem como erro, não como falha
  silenciosa.
- **Subagentes especializados**: o Jarvis escolhe internamente, por
  palavra-chave, entre JarvisDeveloper/Researcher/System/Productivity/Files/
  Business (Mercado Pago) — tudo ainda dentro de UMA ÚNICA chamada ao LLM (sem custo extra de API, sem
  latência a mais). Cada especialista aplica três coisas nessa mesma chamada:
  um tom/foco de resposta (como antes), uma lista de ferramentas priorizadas
  (`preferred_tools` — só reordena a lista mandada pro LLM, nunca remove
  nenhuma) e, em Sistema e Produtividade, um dado real e local injetado direto
  no prompt (CPU/RAM/disco atuais, ou quantos lembretes estão pendentes) —
  então perguntas simples desses temas às vezes nem precisam de uma tool call
  a mais. O especialista escolhido em cada mudança de modo fica registrado no
  painel "Atividade recente" ("Modo especialista: JarvisSystem", etc.) e
  também disponível para a interface via `active_specialist` no snapshot
  (`interface_web/bridge.py`). Ver `core/specialists.py`.
- **Controle de reprodução do Spotify** (`spotify_play`/`pause`/`next`/
  `previous`/`set_volume`/`now_playing`/`play_playlist`/`list_playlists`/
  `add_to_queue`/`toggle_shuffle`/`save_current_track`, ou diga "toca
  [música]", "toca [música] da minha playlist [nome]", "toca minha playlist
  [nome]", "mostra minhas playlists", "adiciona [música] na fila", "ativa/
  desativa o shuffle", "curte essa música", "pausa a música", "próxima
  música", "o que está tocando"): diferente de "abre o Spotify" (que só abre
  o app), isso fala direto com a Web API do Spotify. Passos: crie um app
  grátis em
  [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard),
  cadastre a Redirect URI `http://127.0.0.1:8888/callback` nas configurações
  do app, e cole `SPOTIFY_CLIENT_ID`/`SPOTIFY_CLIENT_SECRET` no `.env`. Na
  primeira vez que usar, o Jarvis abre o navegador pedindo pra você autorizar
  — depois disso fica salvo em `.spotify_cache` e não pede de novo. Se você já
  usava uma versão mais antiga do Jarvis, apague o `.spotify_cache` uma vez
  pra reautorizar com as novas permissões (playlists e "Músicas Curtidas").
  **Importante**: tocar/pausar/pular/volume só funcionam com conta Spotify
  **Premium** (é restrição da própria API do Spotify, não do Jarvis); "o que
  está tocando" e listar playlists funcionam no plano grátis. Também precisa
  do app do Spotify aberto em algum dispositivo (PC, celular, alto-falante) —
  senão o Jarvis avisa em vez de travar. A busca por música escolhe, entre os
  resultados, o nome mais parecido com o que você pediu (em vez de sempre
  confiar no 1º resultado da Spotify, que é influenciado pelo seu histórico
  de audição e pode vir bem diferente do que você pediu).
- **Mercado Pago** (`mercadopago_vendas_recentes`/`mercadopago_criar_cobranca`/
  `mercadopago_saldo`, ou diga "quais foram minhas vendas recentes", "cria
  uma cobrança de R$50 pro João", "qual meu saldo no mercado pago"): gere um
  Access Token grátis em
  [mercadopago.com.br/developers/panel](https://www.mercadopago.com.br/developers/panel)
  → "Suas integrações" → crie uma aplicação → aba Credenciais (produção ou
  teste) → copie o Access Token e cole em `MERCADOPAGO_ACCESS_TOKEN` no
  `.env`. Vendas recentes e criação de cobrança (link de pagamento) são
  consultas diretas à API, praticamente instantâneas; já o *saldo* é
  diferente — o Mercado Pago não tem um endpoint de "quanto eu tenho agora",
  só um relatório de liquidação gerado sob demanda (pode levar alguns
  segundos a minutos). `mercadopago_saldo` pede esse relatório e espera um
  pouco; se não ficar pronto a tempo, o Jarvis avisa isso claramente em vez
  de inventar um número — o valor mostrado é o líquido liquidado no período,
  não o saldo instantâneo da carteira. Criar uma cobrança sempre pede
  confirmação antes de executar (mesmo padrão de `create_issue`/`git_push`).

## Google — Gmail/Calendar/Drive

O Jarvis consegue ler e-mails não lidos, mandar e-mail, ver e criar
compromissos na agenda, e buscar arquivos no Drive — tudo com uma autenticação
só (um único login cobre as três). Diferente do Spotify/Discord (chave direto
no `.env`), o Google usa um arquivo JSON baixado do Google Cloud Console.

Passo a passo pra configurar (grátis, uso pessoal, ~5 minutos):
1. Acesse [console.cloud.google.com/projectcreate](https://console.cloud.google.com/projectcreate)
   e crie um projeto (qualquer nome, ex.: "Jarvis").
2. Em **APIs & Services → Library**, ative estas três: **Gmail API**,
   **Google Calendar API**, **Google Drive API**.
3. Em **APIs & Services → OAuth consent screen**, aba **Audience**: escolha
   **External**, e em **Test users** adicione o seu próprio e-mail do Gmail.
4. Em **APIs & Services → Credentials → Create Client**: tipo **Desktop app**.
   Baixe o JSON gerado e salve como `google_credentials.json` **na pasta do
   projeto**, ao lado do `.env`.
5. Na primeira vez que usar um comando de e-mail/agenda/Drive, o Jarvis abre
   o navegador pedindo pra você autorizar. Como o app não passou pela
   verificação do Google (só faz sentido pra apps públicos, não pra uso
   pessoal), aparece um aviso "O Google não verificou este app" — clique em
   **Avançado → Acessar Jarvis (não seguro)** pra continuar. É esperado, não
   significa que algo está errado.

**Limitação a saber**: enquanto o app ficar nesse modo "Testing" (que é o
normal e gratuito pra uso pessoal), o Google expira o acesso sozinho a cada 7
dias — o Jarvis percebe isso e abre o navegador de novo automaticamente pra
reautorizar, sem travar nem precisar mexer em nada, só clicar de novo.

## Bot do Discord

Dá pra conversar com o Jarvis de fora do PC (do celular, por exemplo) via
mensagem direta (DM) no Discord — `python main.py --discord`. Segurança em
primeiro lugar: o bot ignora silenciosamente qualquer mensagem que não seja
uma DM vinda de `DISCORD_OWNER_ID` (o Jarvis tem ferramentas de risco alto,
como terminal e bloquear o PC — não dá pra deixar qualquer um no Discord
mandar comando pro seu computador). Confirmações de ações de risco (MEDIUM/
HIGH) chegam como mensagem do bot pedindo "sim"/"não", do mesmo jeito que a
caixa de diálogo faria na interface gráfica.

Passo a passo pra configurar:
1. Acesse [discord.com/developers/applications](https://discord.com/developers/applications)
   → **New Application**.
2. Aba **Bot** (barra lateral) → **Reset Token**/**Copy** → cole em
   `DISCORD_BOT_TOKEN` no `.env`.
3. Ainda na aba **Bot**, em **Privileged Gateway Intents**, ative
   **MESSAGE CONTENT INTENT** e salve — sem isso o bot recebe a mensagem
   mas não consegue ler o texto dela.
4. Aba **OAuth2 → URL Generator** → marque o escopo **bot** → permissões
   **Send Messages** + **Read Message History** → abra o link gerado e
   adicione o bot a um servidor seu (o Discord só permite mandar DM pra um
   bot que compartilha um servidor com você — pode ser um servidor privado,
   só seu, criado na hora só pra isso).
5. No Discord, ative o **Modo desenvolvedor** (Configurações do usuário →
   Avançado) pra poder clicar com o botão direito no seu próprio nome →
   **Copiar ID do Usuário** → cole em `DISCORD_OWNER_ID` no `.env`.
6. `python main.py --discord` e mande uma DM pro bot.

## Identidade visual e personalização

- **Logo e paleta**: a interface usa a logo oficial do Jarvis (estrela
  roxa/branca sobre fundo preto) no cabeçalho e como ícone do `.exe`. As
  cores estão em dois lugares hoje, sempre os mesmos valores: para a
  interface principal (pywebview), no `:root { ... }` do topo de
  `interface_web/web/style.css`; para a interface de reserva
  (CustomTkinter), em `interface/theme.py`. Os tons (roxo vivo, roxo
  escuro, lilás claro) vêm extraídos diretamente da logo — para ajustar a
  paleta inteira de uma vez, edite os dois arquivos juntos.
- **Forma de tratamento (`USER_TITLE`)**: por padrão o Jarvis se dirige a
  você como "Senhor" em toda resposta gerada por IA (ex.: "Pronto, Senhor.").
  Isso é injetado no prompt do sistema em toda mensagem — não depende da
  memória de longo prazo "achar relevante" o pedido, então vale sempre.
  Troque para "Senhora", "Chefe" etc., ou deixe `USER_TITLE=` vazio no `.env`
  para desligar, a qualquer momento.
- **Memória de longo prazo mais confiável**: o Jarvis agora tenta guardar
  proativamente qualquer fato pessoal que você mencionar em conversa (nome,
  onde mora, preferências, ferramentas que usa etc.) chamando a ferramenta
  `remember_fact` — sem precisar dizer "lembra que" toda vez. Fatos
  repetidos não duplicam a lista de memórias, e ao perguntar algo o Jarvis
  sempre prioriza a informação mais recente. Tudo fica no mesmo banco SQLite
  de sempre (`database/jarvis.db`), que — graças ao ajuste de `BASE_DIR` da
  ETAPA EXE-2 — vive ao lado do `.exe`/projeto e nunca é apagado entre
  execuções.

## Como iniciar

```bat
python main.py            REM interface gráfica
python main.py --text     REM modo texto no terminal
python main.py --voice    REM modo voz
python main.py --debug    REM soma-se a qualquer um dos modos acima
```

## Como configurar o cérebro (LLM)

**Pela interface gráfica (mais fácil):** abra o Jarvis sem nenhum provedor
configurado (`python main.py`) e a tela "Configurar IA" abre sozinha —
escolha o provedor, cole a chave (se precisar de uma) e clique em Salvar. O
botão **⚙ Configurar IA** no topo da janela reabre essa tela a qualquer
momento pra trocar de provedor depois. Isso só edita o mesmo `.env` de
sempre — quem preferir editar manualmente continua podendo.

**Editando o `.env` na mão:** o Jarvis funciona com qualquer um destes —
escolha um só, via `LLM_PROVIDER` no `.env`. Sem nenhum configurado, o
Jarvis avisa isso ao iniciar e continua funcionando normalmente para todos
os comandos que o parser local reconhece
(só não vai ter "conversa livre" com IA).

| Provedor | Custo | Como conseguir a chave |
|---|---|---|
| Claude (`claude`, padrão) | Pago por uso, sem cartão não funciona | https://console.anthropic.com → Settings → API Keys (gere de **dentro** de um Workspace, senão dá erro de "not scoped to a workspace") |
| OpenAI (`openai`) | Pago por uso, sem cartão não funciona | https://platform.openai.com/api-keys |
| **Gemini (`gemini`)** | **Grátis, sem cartão** | https://aistudio.google.com/apikey |
| **Groq (`groq`)** | **Grátis, sem cartão**, respostas bem rápidas | https://console.groq.com/keys |
| Ollama (`local`) | **Grátis, 100% offline** | Nenhuma conta — instale o [Ollama](https://ollama.com) e execute `ollama pull qwen3.5:9b` |

Passo a passo (exemplo com Gemini, o mais recomendado se você não quer pagar
nem instalar nada no PC):

1. Crie a chave grátis em https://aistudio.google.com/apikey
2. No `.env`, defina `LLM_PROVIDER=gemini` e cole a chave em `GEMINI_API_KEY`
3. Rode `python main.py --text` de novo

## Como configurar a voz

- **Falar (TTS)**: por padrão usa Edge TTS (grátis, sem cadastro). Troque
  `EDGE_TTS_VOICE` para outra voz pt-BR se preferir (ex.:
  `pt-BR-FranciscaNeural`). Se quiser 100% offline, use
  `TTS_PROVIDER=pyttsx3`.
- **Ouvir (STT)**: por padrão usa o reconhecimento de voz gratuito do Google
  (só envia o áudio quando você já falou algo, nunca um stream contínuo). Para
  rodar totalmente offline, descomente `faster-whisper` no `requirements.txt`,
  instale, e defina `STT_PROVIDER=whisper`.
- **Wake word / voz contínua ("Jarvis, sim Senhor")**: ver seção dedicada logo
  abaixo.
- **Interromper a fala**: diga "para", "pare", "stop" ou "chega" enquanto o
  Jarvis estiver falando (funciona com os provedores Edge TTS e ElevenLabs;
  pyttsx3 não é interrompível — limitação da própria biblioteca).

## Voz contínua — "Jarvis, sim Senhor" (modo tipo Alexa)

Com isso ligado, o Jarvis fica sempre ouvindo em segundo plano, sem precisar
apertar nada: diga a wake word, ele responde em voz ("Sim, Senhor. O que
deseja?") e aí sim você fala o comando de verdade. Duas formas de ligar:

- **Pela interface gráfica** (recomendado pra uso do dia a dia): abra o
  Jarvis normalmente e ative o interruptor "Voz contínua" na janela — fica
  salvo, então continua ligado da próxima vez que você abrir o Jarvis (veja
  também "Usando o Jarvis só como app").
- **Pelo terminal**, útil pra testar/depurar: `WAKE_WORD_ENABLED=true` no
  `.env` e rode `python main.py --voice`.

1. No `.env` (ou pelo interruptor da interface, que faz isso sozinho):
   ```
   WAKE_WORD_ENABLED=true
   WAKE_WORD=jarvis
   ```
2. (Recomendado) Instale o motor de detecção 100% local e leve, feito
   exatamente pra isso — descomente no `requirements.txt` e instale:
   ```
   pip install openwakeword==0.6.0 numpy==1.26.4
   ```
   Ele já vem com um modelo pronto pra palavra "jarvis" (`hey_jarvis`), baixado
   automaticamente (~1-2MB) na primeira vez que a voz contínua for ativada —
   não precisa treinar nada. **Sem instalar isso, o modo voz contínuo
   continua funcionando** (cai sozinho num jeito mais simples de detectar a
   wake word, baseado no reconhecimento de fala normal), só que de um jeito
   menos eficiente e que, se `STT_PROVIDER=google`, manda pra nuvem pequenos
   trechos de áudio o tempo todo (mesmo sem a wake word ter sido dita) só pra
   checar se a wake word foi dita. Pra esse fallback ficar 100% local também,
   use `STT_PROVIDER=whisper`.
3. Diga "jarvis" — o Jarvis responde e escuta seu comando por até 10 segundos.

Personalização:

- `WAKE_GREETING`: o que o Jarvis fala ao ouvir a wake word. Deixe em branco
  pra ele montar sozinho a partir de `USER_TITLE` (ex.: "Sim, Senhor. O que
  deseja?"; sem `USER_TITLE`, vira só "Sim? O que deseja?").
- `USER_TITLE`: já existia (forma de tratamento), mas agora também define a
  saudação padrão da voz contínua.

Detalhe técnico: enquanto o Jarvis fala a saudação e escuta seu comando, a
detecção da wake word em segundo plano fica travada (não reage de novo até
terminar de processar o comando atual) — assim ele não se autointerrompe nem
reage a um eco da própria voz.

## Como adicionar novos programas

Edite `config/apps.json`:

```json
{
  "discord": "C:\\Users\\SEU_USUARIO\\AppData\\Local\\Discord\\Update.exe",
  "spotify": "C:\\Users\\SEU_USUARIO\\AppData\\Roaming\\Spotify\\Spotify.exe"
}
```

A chave é o nome que você vai falar/digitar (minúsculas). Se o programa já
estiver no PATH do Windows, nem precisa cadastrar — o Jarvis encontra sozinho.

Você também pode ensinar por voz/texto: `"lembra que meu editor é o VS Code"`
e depois `"abre meu editor"` — o Jarvis resolve pela memória de longo prazo.

## Como criar uma nova ferramenta

1. Crie `tools/minha_ferramenta.py`:

```python
from core.permissions import RiskLevel
from tools.base import Tool, ToolResult


def minha_acao(parametro: str, **_: object) -> ToolResult:
    # ... faça algo real aqui ...
    return ToolResult(success=True, message="Feito.")


def register(registry) -> None:
    registry.register(Tool(
        name="minha_acao",
        description="Explique para o LLM quando usar esta ferramenta.",
        parameters={"type": "object", "properties": {"parametro": {"type": "string"}}, "required": ["parametro"]},
        risk_level=RiskLevel.LOW,
        handler=minha_acao,
    ))
```

2. Registre em `tools/registry.py` (adicione o módulo à lista em
   `build_default_registry`).
3. (Opcional) Adicione um padrão em `core/intent.py` para o comando não
   precisar passar pelo LLM.

## Como gerar o Jarvis.exe

Um `.exe` Windows só pode ser gerado rodando no Windows de verdade (não dá
pra fazer isso de fora) — mas o script já está pronto, é só rodar:

1. Abra o PowerShell **na pasta do projeto**, com o venv ativado (o mesmo de
   sempre, onde `python main.py --text` já funciona)
2. Rode:
   ```powershell
   .\build.bat
   ```
   Ele instala o PyInstaller automaticamente se faltar, gera o `.exe`, e
   copia o `.env.example` e o `config/apps.json` pra perto dele.
3. O resultado fica em `dist\Jarvis.exe`. Pode mover a pasta `dist` inteira
   pra onde quiser (Área de Trabalho, por exemplo) — só não separe o `.exe`
   dos arquivos que ficam do lado dele.
4. (Opcional) Dentro da pasta `dist`, rode `criar_atalho.bat` pra criar um
   atalho do Jarvis direto na sua Área de Trabalho.

Na primeira vez que abrir o `Jarvis.exe`, a tela "Configurar IA" abre
sozinha (mesma tela da interface gráfica normal) — não precisa editar nada
na mão. O Tesseract OCR e o Ollama, se você quiser usá-los, continuam sendo
instalados à parte — nenhum `.exe` resolve isso, já que são programas
externos de verdade, não bibliotecas Python. O mesmo vale pro WebView2
Runtime que a interface principal usa (veja "Solução de problemas" caso a
janela abra em branco) — quase sempre já vem instalado no Windows, então
na prática isso raramente aparece.

Se o build travar com algum "ModuleNotFoundError" ao *abrir* o `.exe` (não
ao gerar), normalmente é uma biblioteca "escondida" que o PyInstaller não
detectou sozinho — me avisa qual biblioteca faltou, é só adicionar o nome
dela em `hiddenimports` no `jarvis.spec` e rodar `build.bat` de novo.

## Usando o Jarvis só como app (.exe)

Pra usar o Jarvis puramente como um programa instalado — sem nunca precisar
abrir um terminal, digitar comando nenhum, ou lembrar que ele existe —, três
coisas trabalham juntas:

- **Ícone na bandeja do Windows**: clicar no X da janela não fecha mais o
  Jarvis, só minimiza pra bandeja (perto do relógio), do mesmo jeito que
  WhatsApp/Discord/Spotify. Ele continua rodando (e ouvindo, se a voz
  contínua estiver ligada) em segundo plano. Clique no ícone da bandeja (ou
  no menu "Abrir Jarvis") pra trazer a janela de volta; "Sair" no menu da
  bandeja encerra o Jarvis de verdade. Requer `pip install pystray` (já no
  `requirements.txt`) — sem isso instalado, o X da janela volta a fechar o
  programa normalmente, como antes.
- **Voz contínua direto na interface**: na página "Visão geral", card
  "Automação", tem um interruptor "Voz contínua" — liga o modo "diga
  'jarvis' antes do comando" sem precisar rodar `python main.py --voice`
  num terminal à parte. Fica salvo (usa o mesmo `WAKE_WORD_ENABLED` do
  `.env`), então volta ligado sozinho da próxima vez que você abrir o
  Jarvis.
- **Iniciar com o Windows**: só aparece dentro do `Jarvis.exe` já gerado
  (não faz sentido em `python main.py`, que depende do venv/caminho do
  projeto). No mesmo card "Automação" da "Visão geral", um interruptor
  "Iniciar com o Windows" cadastra o Jarvis pra abrir sozinho (direto
  minimizado na bandeja) toda vez que você liga o computador — usa só a
  chave de registro do seu próprio usuário (`HKEY_CURRENT_USER`), não
  precisa rodar como administrador.

Juntando os três: gere o `.exe` (seção acima), abra uma vez, ligue "Voz
contínua" e "Iniciar com o Windows" no card "Automação" da "Visão geral" —
a partir daí o Jarvis some da barra de tarefas, mas continua ligado e
ouvindo "jarvis" em segundo plano, sempre que o computador estiver ligado,
sem você precisar abrir nada de novo.

## Solução de problemas

| Sintoma | Causa provável | Solução |
|---|---|---|
| "ANTHROPIC_API_KEY não definida" | Sem chave no `.env` | Normal — só limita a conversa livre; comandos locais funcionam |
| Modo voz diz que não achou microfone | Falta `pyaudio`/driver de áudio | `pip install pyaudio`; no Windows pode precisar do PyAudio pré-compilado (`pip install pipwin && pipwin install pyaudio`) |
| "Voz contínua" avisa que não achou microfone logo ao abrir (principalmente com "Iniciar com o Windows" ligado) | Falha passageira — o driver de áudio do Windows pode ainda não estar pronto no instante em que o Jarvis checa o microfone | Espere alguns segundos e ligue o interruptor de novo (o Jarvis já tenta de novo sozinho depois de um curto cooldown, em vez de travar "sem microfone" pro resto da execução) |
| Log enche de `Erro capturando áudio: 'NoneType' object does not support the context manager protocol`, repetido sem parar | Bug corrigido: na voz contínua, o processamento do comando rodava numa thread separada e o detector de wake word não esperava isso terminar — as duas ficavam disputando o microfone ao mesmo tempo | Já corrigido (o processamento agora é síncrono, o detector só volta a ouvir depois que o comando anterior termina de verdade) — atualize para esta versão do `jarvis.zip` |
| `pip install -r requirements.txt` falha tentando compilar o `pygame` do zero, com `ModuleNotFoundError: No module named 'setuptools._distutils.msvccompiler'` | Python muito novo (3.14+) — o `pygame` original não lança instalador pronto pra ele desde 2024, então o pip tenta compilar do zero e quebra num módulo interno que o `setuptools` removeu | Já corrigido: trocamos pra `pygame-ce` (continuação mantida do mesmo projeto, com instalador pronto pras versões novas do Python, sem mudar nada no código) — atualize para esta versão do `requirements.txt` e rode `pip install -r requirements.txt` de novo |
| `pip install -r requirements.txt` falha em vários pacotes ao mesmo tempo (ex.: `pillow`, `pyaudio`, `winsdk`) com `Building windows wheels requires Microsoft Visual Studio` ou `scikit-build could not get a working generator` | Python muito novo pro ecossistema — nenhum desses pacotes ainda tem instalador pronto pra essa versão do Python, principalmente o `winsdk` (usado pelas notificações do Windows), que hoje só tem instalador pronto até Python 3.12 | Use Python 3.12 pra este projeto (veja "Requisitos" acima) — crie o venv com `py -3.12 -m venv .venv` em vez de `python -m venv .venv`. Trocar versão de pacote não resolve o `winsdk` sozinho; só o Python 3.12 resolve tudo de uma vez |
| Jarvis abre mas avisa `Não consegui inicializar o microfone (No module named 'distutils')` | O pacote `SpeechRecognition` (mesmo já no Python 3.12) tentava, numa versão antiga, importar o módulo `distutils` — removido do Python desde a versão 3.12 — só pra checar a versão do `pyaudio` instalado | Já corrigido: trocamos pra `SpeechRecognition>=3.11.0` no `requirements.txt` (versão que removeu esse import) — rode `pip install -r requirements.txt` de novo pra pegar a atualização |
| Abrir o Spotify pelo Jarvis leva a uma página do Spotify que mostra só o texto `client_id: Invalid` | O `SPOTIFY_CLIENT_ID` no `.env` está com algum caractere faltando/errado (um Client ID do Spotify sempre tem exatamente 32 caracteres) — geralmente por ter sido digitado/colado incompleto | Volte em https://developer.spotify.com/dashboard, abra seu app, clique no Client ID pra ele mostrar o valor completo e copie de novo (selecione tudo em vez de digitar); cole o valor certo em `SPOTIFY_CLIENT_ID=` no `.env` |
| Voz sai muda e o log mostra `Falha no Edge TTS: [Errno 13] Permission denied ...jarvis_tts_output.mp3` toda vez que o Jarvis fala | Bug corrigido: no Windows, `pygame` mantém o arquivo de áudio da fala anterior aberto/travado até ser explicitamente liberado — como cada fala nova tentava gravar em cima do mesmo arquivo, o Windows recusava por ele "ainda estar em uso" (o Linux/Mac deixam sobrescrever, por isso nunca apareceu fora do Windows) | Já corrigido (o player libera o arquivo da fala anterior antes de gravar a próxima) — atualize para esta versão do `jarvis.zip` |
| Log mostra `Erro capturando áudio: This audio source is already inside a context manager` (geralmente com a voz contínua ligada) | Bug corrigido: o botão de microfone manual e o detector de wake word, rodando ao mesmo tempo, podiam tentar usar o mesmo microfone simultaneamente — a biblioteca de voz não permite isso | Já corrigido (agora, se o microfone já estiver em uso por outra captura, a segunda chamada só desiste dessa vez em vez de quebrar) — atualize para esta versão do `jarvis.zip` |
| Volume/mute não funciona | Falta `pycaw`/`comtypes` | `pip install pycaw comtypes` (Windows apenas) |
| Print de tela falha | Falta `pillow` | `pip install pillow` |
| Busca na internet falha | Falta `duckduckgo-search` ou sem internet | `pip install duckduckgo-search` |
| "Ainda não tenho a ferramenta X implementada" | Comando reconhecido mas sem tool cadastrada | Veja "Como criar uma nova ferramenta" |
| Interface gráfica abre uma janela em branco, ou aparece um aviso sobre WebView2 | Falta o WebView2 Runtime (raro — o Windows 11 e a maioria das instalações atuais do Windows 10 já vêm com ele) | Baixe o "Evergreen Bootstrapper" em https://developer.microsoft.com/microsoft-edge/webview2/ e instale (é rapidinho); se preferir não instalar nada, desinstale `pywebview` (`pip uninstall pywebview`) que o Jarvis cai sozinho pra interface CustomTkinter de reserva |
| Interface gráfica não abre de jeito nenhum (nem a versão pywebview, nem a de reserva) | Falta `pywebview` e `customtkinter` | `pip install -r requirements.txt` de novo (ou, manualmente, `pip install pywebview customtkinter`) |
| Voz sai "muda" (aparece `Falha no Edge TTS: 403, message='Invalid response status'` no log) | Edge TTS é uma API não-oficial (imita o navegador Edge por dentro) e a Microsoft muda a validação dela de vez em quando, quebrando versões antigas do pacote | `pip install -U edge-tts` (o `requirements.txt` já não trava mais numa versão fixa por causa disso). Enquanto isso, o Jarvis já cai sozinho pro `pyttsx3` (voz robótica, mas 100% offline e nunca falha) em vez de ficar mudo |
| Você fala (pelo botão do microfone ou depois da wake word) e **nada acontece** — sem resposta, sem erro na tela | Bug corrigido: antes, qualquer falha ao reconhecer a fala (nenhum áudio detectado, áudio captado mas não entendido, erro de captura) ficava muda, sem nenhum aviso — todas pareciam "o microfone não reconhece" | Já corrigido: agora o Jarvis sempre avisa o motivo específico ("Não ouvi nada" = mic errado/baixo no Windows ou começou a falar cedo/tarde demais; "ouvi mas não consegui entender" = tente falar mais devagar e perto do microfone). Também aumentamos a calibração inicial de ruído ambiente de 0.5s para 1s, pra reduzir falso "não ouvi nada" por causa de um pico de ruído bem na hora em que o Jarvis abre. Atualize para esta versão do `jarvis.zip`; se a mensagem persistir, confira em Configurações do Windows > Som > Entrada se o microfone certo está selecionado como padrão e com o volume de entrada adequado |

## Segurança

- Toda ação passa pelo `PermissionManager` (`core/permissions.py`).
- `LOW_RISK` executa direto; `MEDIUM_RISK`/`HIGH_RISK` pedem confirmação
  explícita (sim/não no console, ou diálogo na interface gráfica).
- `CRITICAL` fica bloqueado por padrão — mesmo ativando
  `ALLOW_CRITICAL_ACTIONS=true`, uma lista fixa de comandos catastróficos
  (formatar disco, `rm -rf`/`del /s /q` recursivo, `diskpart`, edição de
  registro crítico, fork bomb, etc. — veja `tools/shell.py`) **nunca** roda,
  ponto final, sem exceção.
- O Jarvis nunca envia, paga, publica, desliga/reinicia o PC ou apaga arquivos
  sozinho sem confirmação.
- Segredos ficam só no `.env` (fora do controle de versão).
- Logs (`logs/jarvis.log`) nunca gravam chaves de API, senhas ou tokens.
- A área de transferência nunca é persistida no banco de dados.

## Roadmap

**Já entregue** (além do protótipo inicial): API do GitHub (repos/issues),
visão computacional/OCR de tela, tool-calling completo em modelo local via
Ollama, subagentes especializados (JarvisDeveloper/Researcher/System/
Productivity/Files), provedores de IA gratuitos sem cartão (Gemini/Groq),
tela de configuração de IA na interface gráfica (sem precisar editar `.env`
na mão).

**Preparação para virar `.exe`** — só falta você rodar no seu Windows
(veja "Como gerar o Jarvis.exe" abaixo):
- [x] Corrigir "abre meu X" com possessivo pra resolver igual "abre o X"
- [x] Caminhos de app instalados em pasta versionada (ex.: Discord) resolvem
      a versão mais recente sozinhos, sem quebrar a cada atualização
- [x] Tela de configuração de IA na interface gráfica (não depende mais de
      editar `.env` na mão)
- [x] `BASE_DIR` agora detecta quando está rodando como `.exe` (PyInstaller)
      e usa a pasta do `.exe`, não uma pasta temporária — sem isso, o
      `.env`/banco de dados/logs "sumiriam" a cada vez que o programa fechasse
- [x] Ícone customizado do Jarvis (`assets/icon.ico`)
- [x] Script de build com PyInstaller (`jarvis.spec` + `build.bat`) — só falta
      **você** rodar, porque um `.exe` Windows só pode ser gerado num Windows
      de verdade
- [x] Script pra criar atalho na Área de Trabalho (`criar_atalho.bat`)

**Já entregue (Jarvis como app, não só um `.exe` que abre uma janela)**:
ícone na bandeja do Windows (fechar a janela minimiza em vez de encerrar,
igual WhatsApp/Discord/Spotify — requer `pystray`), voz contínua ligável
direto por um interruptor na interface (sem precisar de terminal), início
automático com o Windows (interruptor próprio, só disponível dentro do
`Jarvis.exe` gerado). Veja "Usando o Jarvis só como app (.exe)" acima.

**Já entregue (rodada de personalização)**: logo oficial e paleta roxo/preto
em toda a interface (`interface/theme.py`), memória de longo prazo mais
robusta (guarda fatos proativamente, sem duplicar, sempre prioriza o mais
recente), forma de tratamento configurável (`USER_TITLE`, padrão "Senhor"),
controle de reprodução do Spotify (tocar/pausar/pular/volume/música atual),
fallback automático entre provedores de IA (Gemini→Groq→Ollama — antes
adiado para uma "versão 3.0", já funcionando), bot do Discord pra conversar
com o Jarvis de fora do PC (`python main.py --discord`), e integração com
Google — Gmail/Calendar/Drive (ler/mandar e-mail, ver/criar compromisso,
buscar arquivo).

**Já entregue (voz contínua)**: modo "sempre ouvindo" tipo Alexa
(`WAKE_WORD_ENABLED=true` + `python main.py --voice` — diga "jarvis", o
Jarvis responde em voz e aí escuta o comando), com detecção 100% local via
openWakeWord (modelo pronto `hey_jarvis`) e fallback automático caso a lib
não esteja instalada. Veja a seção "Voz contínua" acima.

**Ainda não implementado**: Home Assistant, WhatsApp (sem API oficial
gratuita) e Telegram como canais de mensagem, automação de tarefas por
gravação/repetição de ações (macro record/replay), controle do Jarvis pelo
celular, Trello, câmeras/smart home, controle de celular Android, atalhos
globais de teclado, ícone na bandeja do Windows (systray — o `.exe` ainda
abre como janela normal, sem minimizar pra bandeja), RAG com banco vetorial.

## Rodando os testes

```bat
pytest
```
## Kali Linux

O modo recomendado no Kali é headless: no login, uma unidade `systemd --user`
executa `python main.py --background`. Esse caminho não importa `pywebview` nem
CustomTkinter, não abre dashboard, navegador ou terminal e espera eventos sem
busy loop. O fluxo de áudio é wake word → STT → agente/tools → TTS → wake word.
O LLM só recebe texto depois da transcrição.

### 1. Dependências do sistema

O instalador não executa `sudo`, `apt install` ou `curl | sh`. No Kali/Debian,
revise e execute manualmente o que for necessário:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip python3-dev build-essential \
  portaudio19-dev libasound2-dev ffmpeg libespeak1 xdg-utils pulseaudio-utils
```

PipeWire pode fornecer `wpctl`; quando ele não existe, o JARVIS usa `pactl`.
Para abrir caminhos e URLs é necessário `xdg-open` (`xdg-utils`). Dependências
Windows (`pycaw`, `comtypes`, `win11toast`) têm markers e não são instaladas no
Linux.

### 2. Ambiente Python e openWakeWord

Da pasta `JARVIS`:

```bash
chmod +x scripts/setup_kali.sh scripts/install_linux_service.sh scripts/uninstall_linux_service.sh
./scripts/setup_kali.sh
test -e .env || cp .env.example .env
```

O script cria `.venv`, instala `requirements.txt` e verifica áudio/Ollama. O
`openwakeword` usa por padrão o modelo acústico `hey_jarvis`, enquanto a palavra
mostrada ao usuário permanece `WAKE_WORD=jarvis`. Um modelo customizado futuro
pode ser selecionado por `WAKE_WORD_MODEL`.

### 3. Ollama e Qwen3.5 9B

Instale o Ollama seguindo a documentação oficial do projeto e confirme que o
serviço responde. O setup não instala o Ollama e nunca baixa modelos sem sua
ação explícita:

```bash
ollama serve
ollama pull qwen3.5:9b
ollama list
```

Configuração recomendada no `.env`:

```dotenv
LLM_PROVIDER=local
LOCAL_LLM_URL=http://127.0.0.1:11434
LOCAL_LLM_MODEL=qwen3.5:9b
LOCAL_LLM_CONTEXT=8192
LOCAL_LLM_TIMEOUT=180
LOCAL_LLM_TEMPERATURE=0.6
LOCAL_LLM_THINKING=false
OLLAMA_KEEP_ALIVE=15m
```

O health check distingue Ollama offline, servidor online, modelo ausente,
modelo pronto e erro do modelo. CPU, GPU ou uso híbrido são decisões do Ollama;
o JARVIS não força backend.

### 4. ROTINA e ROTINA_KEY

O projeto `ROTINA` deve ficar ao lado de `JARVIS`, ou ter seu diretório definido
em `ROTINA_DIR`. Faça a configuração inicial manual uma vez:

```bash
cd ../ROTINA
python3 server.py
```

Abra `http://127.0.0.1:8765`, crie a senha inicial e copie a chave exibida para
o `.env` do JARVIS. Não coloque essa chave no README, em testes ou commits:

```dotenv
ROTINA_ENABLED=true
ROTINA_URL=http://127.0.0.1:8765
ROTINA_KEY=
ROTINA_DIR=
ROTINA_AUTO_START=true
ROTINA_STOP_ON_EXIT=false
```

Com auto-start ligado, o JARVIS reutiliza um servidor já ativo ou inicia
`server.py --no-browser` em background. Por padrão ele não encerra o ROTINA no
shutdown. Todas as leituras/escritas passam pela API com `X-Api-Key`; o JARVIS
nunca edita `data.json` diretamente. O resumo semanal está em
`GET /api/summary?period=week`.

### 5. Teste manual e diagnóstico

```bash
.venv/bin/python main.py --doctor
.venv/bin/python main.py --text
.venv/bin/python main.py --background --debug
```

No último comando, diga “Jarvis”, aguarde “Estou ouvindo”, fale o comando e use
`Ctrl+C` para encerrar. O modo background nunca abre GUI. Para testar sem áudio,
use `--text`. O diagnóstico não mostra tokens ou chaves.

### 6. Instalar e operar o serviço systemd do usuário

```bash
./scripts/install_linux_service.sh
systemctl --user status jarvis
systemctl --user start jarvis
systemctl --user stop jarvis
systemctl --user restart jarvis
journalctl --user -u jarvis
journalctl --user -u jarvis -f
```

O instalador descobre o diretório atual e o Python do `.venv`, gera
`~/.config/systemd/user/jarvis.service`, recarrega, habilita e reinicia a
unidade. Para remover somente a unidade, preservando `.env`, banco, memória e
logs:

```bash
./scripts/uninstall_linux_service.sh
```

### 7. Logs e áudio

Eventos principais aparecem em `journalctl` e em `logs/jarvis.log`. Chaves,
cookies e tokens não são registrados. Se o microfone não aparecer:

```bash
arecord -l
pactl list short sources
wpctl status
```

Confira também se o usuário da sessão tem acesso ao dispositivo e se o servidor
PipeWire/PulseAudio está ativo. Se `pyaudio` falhar na instalação, confirme
`portaudio19-dev`, `python3-dev` e `build-essential`. Se o Edge TTS não tiver
rede, configure `TTS_PROVIDER=pyttsx3`; para STT totalmente local, instale
`faster-whisper` e use `STT_PROVIDER=whisper`.
