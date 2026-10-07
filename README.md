# 🤖 JARVIS   AUTOMATIZANDO TUDO NESSA PORRA

<p align="center">
  Assistente pessoal inteligente para Linux, desenvolvido para integrar voz, inteligência artificial, automações, ferramentas externas e um sistema de orquestração multiagente.
</p>

---

## 📌 Sobre o projeto

**JARVIS** é um assistente pessoal desenvolvido para funcionar principalmente em **Linux**, com suporte a interação por voz, execução de comandos, uso de diferentes modelos de IA e integração com ferramentas externas.

O objetivo do projeto é centralizar diferentes recursos de inteligência artificial em um único sistema, evitando depender de apenas um modelo para todas as tarefas.

O JARVIS utiliza uma arquitetura modular, permitindo adicionar novas IAs, ferramentas e plugins sem precisar reconstruir todo o sistema.

---

## ✨ Principais recursos

- 🎙️ Interação por voz
- 🗣️ Palavra de ativação do assistente
- 🧠 Processamento com inteligência artificial
- ⚡ Fast Router para comandos simples
- 🤖 Integração com múltiplas IAs
- 🧩 Sistema de plugins
- 🔀 Orquestração inteligente através do **NEXUS**
- 💻 Integração com ferramentas de programação
- 🧠 Cache para reduzir chamadas desnecessárias de IA
- 🔐 Controle de APIs e variáveis de ambiente
- 📂 Execução de funções locais
- 📊 Integração com o sistema ROTINA
- 📝 Possibilidade de integração com Notion
- 🐙 Integração com GitHub
- 🔌 Estrutura preparada para novas ferramentas
- 🐧 Desenvolvido principalmente para Linux

---

## 🧠 Arquitetura

A arquitetura simplificada é:

```text
                         ┌────────────────────┐
                         │       USUÁRIO      │
                         └─────────┬──────────┘
                                   │
                          Voz / Texto / Comando
                                   │
                         ┌─────────▼──────────┐
                         │      JARVIS        │
                         │  Interface Central │
                         └─────────┬──────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │        FAST ROUTER          │
                    │ Comandos simples/localmente │
                    └──────────────┬──────────────┘
                                   │
                     tarefa precisa de IA?
                           │              │
                         NÃO             SIM
                           │              │
                    execução local       ▼
                                   ┌──────────────┐
                                   │    NEXUS     │
                                   │ Orquestrador │
                                   └──────┬───────┘
                                          │
                    ┌─────────────────────┼─────────────────────┐
                    │                     │                     │
                  Codex                 Claude            Outras IAs
                    │                     │                     │
             programação          análise/raciocínio      identificação
                                                        e roteamento
                                                        Grok / Mistral
```

---

## 🔀 NEXUS

O **NEXUS** funciona como uma camada de orquestração entre o JARVIS e as ferramentas de inteligência artificial.

Em vez de enviar todas as tarefas para a mesma IA, o NEXUS pode identificar a categoria da solicitação e encaminhá-la para a ferramenta mais apropriada.

Exemplo:

```text
"Corrija esse código"
        ↓
      NEXUS
        ↓
      CODEX
```

Outro exemplo:

```text
"Analise esse documento"
        ↓
      NEXUS
        ↓
     CLAUDE
```

Ou:

```text
"Qual ferramenta deve resolver essa tarefa?"
        ↓
      NEXUS
        ↓
 GROK / MISTRAL
        ↓
seleção da ferramenta
```

Essa arquitetura tem como objetivo:

- diminuir consumo desnecessário de tokens;
- reduzir chamadas de IA;
- utilizar modelos especializados;
- melhorar velocidade;
- facilitar expansão futura.

---

## 💻 Sistemas recomendados

O projeto foi desenvolvido principalmente para:

### Recomendado

```text
Linux Mint
Ubuntu
Debian
```

Também pode funcionar em outras distribuições Linux baseadas em Debian.

---

## ⚙️ Requisitos

Recomendado:

```text
Python 3.10+
Git
pip
venv
FFmpeg
PortAudio
ALSA
```

Para verificar:

```bash
python3 --version
git --version
pip3 --version
```

---

# 🚀 Instalação no Linux

## 1. Atualizar o sistema

Abra o terminal:

```bash
sudo apt update
sudo apt upgrade -y
```

## 2. Instalar dependências básicas

```bash
sudo apt install -y \
git \
python3 \
python3-pip \
python3-venv \
python3-dev \
build-essential \
ffmpeg \
portaudio19-dev \
libasound2-dev
```

## 3. Clonar o JARVIS

```bash
git clone https://github.com/limazk/JARVIS.git
```

Entre na pasta:

```bash
cd JARVIS
```

Confira os arquivos:

```bash
ls
```

## 4. Criar ambiente virtual Python

Isso evita conflitos com os pacotes do Linux.

```bash
python3 -m venv .venv
```

Ative:

```bash
source .venv/bin/activate
```

O terminal deverá mostrar algo semelhante a:

```text
(.venv) usuario@linux:~/JARVIS$
```

## 5. Atualizar o pip

```bash
python -m pip install --upgrade pip
```

## 6. Instalar dependências do JARVIS

Se existir:

```text
requirements.txt
```

execute:

```bash
pip install -r requirements.txt
```

---

# 🎤 Configuração do microfone

Liste os dispositivos:

```bash
arecord -l
```

Teste uma gravação:

```bash
arecord -d 5 teste.wav
```

Reproduza:

```bash
aplay teste.wav
```

Se conseguir ouvir sua voz, o microfone está funcionando.

---

# 🔊 Testar áudio do Linux

Execute:

```bash
speaker-test -c 2
```

Interrompa com:

```text
CTRL + C
```

---

# 🔐 Configuração das APIs

Nunca coloque chaves de API diretamente no código ou envie arquivos contendo chaves para o GitHub.

Crie:

```bash
nano .env
```

Exemplo:

```env
# ==========================
# JARVIS
# ==========================

JARVIS_NAME=Jarvis
JARVIS_LANGUAGE=pt-BR

# ==========================
# GROK
# ==========================

GROK_API_KEY=

# ==========================
# MISTRAL
# ==========================

MISTRAL_API_KEY=

# ==========================
# ANTHROPIC / CLAUDE
# ==========================

ANTHROPIC_API_KEY=

# ==========================
# OPENAI
# ==========================

OPENAI_API_KEY=

# ==========================
# NOTION
# ==========================

NOTION_TOKEN=
```

Nem todas as chaves são obrigatórias.

Você só precisa adicionar aquelas referentes às ferramentas que pretende utilizar.

---

# ⚠️ Proteja o `.env`

Confirme que existe um `.gitignore`.

Ele deve conter:

```gitignore
.env
.venv/
venv/
__pycache__/
*.pyc
*.log
.DS_Store
```

Nunca faça:

```bash
git add .env
```

---

# 🤖 Codex

Caso o Codex CLI faça parte da instalação:

confirme:

```bash
codex --version
```

Se já estiver autenticado:

```bash
codex
```

O NEXUS poderá utilizar o Codex principalmente para tarefas relacionadas a:

- programação;
- correção de bugs;
- análise de repositórios;
- edição de arquivos;
- implementação de funcionalidades;
- refatoração.

---

# 🧠 Claude

Caso utilize Claude CLI ou API, ele poderá ser usado para:

- análise complexa;
- documentos;
- arquitetura;
- raciocínio;
- revisão;
- planejamento.

O método de autenticação dependerá da implementação configurada no JARVIS.

---

# 🌐 Grok

No projeto, o Grok pode ser utilizado como uma ferramenta auxiliar de interpretação e classificação.

Exemplo:

```text
Solicitação
      ↓
    GROK
      ↓
categoria da tarefa
      ↓
    NEXUS
```

---

# 🧠 Mistral

O Mistral também pode atuar na camada de interpretação e roteamento.

O objetivo é evitar utilizar modelos mais caros para simplesmente identificar qual ferramenta deve receber uma tarefa.

---

# ▶️ Como iniciar o JARVIS

Primeiro:

```bash
cd ~/JARVIS
```

Ative o ambiente:

```bash
source .venv/bin/activate
```

Depois execute o inicializador existente no projeto.

Se existir:

```text
start.sh
```

use:

```bash
chmod +x start.sh
./start.sh
```

Se o projeto utilizar um arquivo Python principal, normalmente será algo como:

```bash
python main.py
```

ou:

```bash
python3 main.py
```

Você pode verificar os arquivos disponíveis com:

```bash
ls
```

---

# 🎙️ Utilizando o JARVIS

Depois de iniciado, o sistema fica aguardando interação.

Dependendo da configuração de wake word, você poderá utilizar:

```text
Jarvis
```

ou:

```text
Hey Jarvis
```

seguido do comando.

Exemplo:

```text
Jarvis, abra o Spotify.
```

```text
Jarvis, quanto eu ganhei hoje?
```

```text
Jarvis, analise meu projeto.
```

```text
Jarvis, peça para o Codex corrigir esse código.
```

---

# 💡 Fast Router

Nem todo comando precisa passar por um modelo de linguagem.

Por exemplo:

```text
Jarvis, que horas são?
```

pode ser resolvido diretamente.

Fluxo:

```text
Usuário
   ↓
Fast Router
   ↓
Resposta local
```

Isso melhora:

- velocidade;
- consumo de tokens;
- estabilidade;
- custo.

---

# 💾 Cache

O JARVIS pode utilizar cache para evitar processamento repetitivo.

Exemplo:

```text
usuário pergunta informação
        ↓
consulta realizada
        ↓
resultado armazenado
        ↓
nova consulta semelhante
        ↓
cache
```

O cache pode utilizar TTL para evitar que informações antigas permaneçam indefinidamente.

---

# 📊 ROTINA

O sistema ROTINA pode ser integrado ao JARVIS para consultas relacionadas a informações pessoais registradas no sistema.

Exemplo:

```text
Jarvis, quanto eu ganhei hoje?
```

O fluxo ideal:

```text
JARVIS
   ↓
ROTINA
   ↓
dados locais/banco
   ↓
resposta
```

Com isso, não é necessário enviar toda consulta para um LLM.

---

# 🧩 Plugins

A arquitetura foi preparada para permitir integrações adicionais.

Exemplos:

```text
GitHub
Notion
Trello
Google Calendar
Google Drive
Spotify
APIs externas
automação do Linux
```

Cada plugin deve ficar isolado do núcleo principal sempre que possível.

Exemplo:

```text
jarvis/
│
├── core/
├── nexus/
├── plugins/
│   ├── github/
│   ├── notion/
│   ├── trello/
│   └── ...
│
├── services/
├── config/
└── main.py
```

A estrutura real pode variar conforme a versão atual do projeto.

---

# 📝 Notion

Para usar Notion através da API:

1. crie uma integração no Notion;
2. copie o token;
3. compartilhe a página desejada com a integração;
4. adicione o token ao `.env`.

Exemplo:

```env
NOTION_TOKEN=seu_token
```

---

# 🐙 GitHub

O JARVIS também pode ser integrado ao GitHub para:

- analisar código;
- acessar projetos;
- acompanhar alterações;
- trabalhar com issues;
- criar commits;
- auxiliar no desenvolvimento.

Nunca coloque tokens GitHub diretamente no código.

---

# 🔄 Atualizando o JARVIS

Entre no diretório:

```bash
cd ~/JARVIS
```

Baixe as atualizações:

```bash
git pull origin main
```

Ative novamente o ambiente:

```bash
source .venv/bin/activate
```

Atualize as dependências:

```bash
pip install -r requirements.txt
```

---

# 🛑 Como desligar o JARVIS

Se estiver rodando diretamente no terminal:

```text
CTRL + C
```

Se o processo continuar:

```bash
ps aux | grep -i jarvis
```

Depois:

```bash
kill PID
```

Se necessário:

```bash
kill -9 PID
```

Também é possível:

```bash
pkill -f jarvis
```

Use `pkill` apenas quando tiver certeza de que deseja encerrar todos os processos relacionados ao JARVIS.

---

# 🔎 Ver processos

```bash
ps aux | grep -i jarvis
```

Para Python:

```bash
ps aux | grep python
```

---

# 🐛 Problemas comuns

## `python: command not found`

Use:

```bash
python3 --version
```

Execute:

```bash
python3 main.py
```

## `pip: command not found`

```bash
sudo apt install python3-pip
```

## `No module named ...`

Ative o ambiente:

```bash
source .venv/bin/activate
```

Depois:

```bash
pip install -r requirements.txt
```

## Problema com PyAudio

Instale:

```bash
sudo apt install portaudio19-dev python3-dev
```

Depois:

```bash
pip install pyaudio
```

## Microfone não funciona

Abra:

```bash
pavucontrol
```

Se não estiver instalado:

```bash
sudo apt install pavucontrol
```

Confirme em:

```text
Input Devices
```

e selecione o microfone correto.

## Áudio não funciona

Verifique:

```bash
pactl info
```

e:

```bash
aplay -l
```

## Permissão negada ao executar `.sh`

```bash
chmod +x nome-do-arquivo.sh
```

Depois:

```bash
./nome-do-arquivo.sh
```

## Git não encontrado

```bash
sudo apt install git
```

## Ambiente virtual não funciona

Instale:

```bash
sudo apt install python3-venv
```

Depois recrie:

```bash
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
```

---

# 🧹 Reinstalação limpa das dependências

Se estiver com muitos problemas:

```bash
cd ~/JARVIS

rm -rf .venv

python3 -m venv .venv

source .venv/bin/activate

pip install --upgrade pip

pip install -r requirements.txt
```

---

# 📥 Instalação resumida

Para usuários que já conhecem Linux:

```bash
sudo apt update

sudo apt install -y \
git \
python3 \
python3-pip \
python3-venv \
python3-dev \
build-essential \
ffmpeg \
portaudio19-dev \
libasound2-dev

git clone https://github.com/limazk/JARVIS.git

cd JARVIS

python3 -m venv .venv

source .venv/bin/activate

pip install --upgrade pip

pip install -r requirements.txt
```

Depois configure:

```text
.env
```

e execute o inicializador da versão instalada.

---

# 🔄 Instalar atualizações posteriormente

```bash
cd ~/JARVIS

git pull

source .venv/bin/activate

pip install -r requirements.txt
```

---

# 🗑️ Desinstalação

Caso tenha instalado somente através do Git:

```bash
cd ~
rm -rf JARVIS
```

Dependências do sistema podem permanecer instaladas.

---

# 🔐 Segurança

Não envie para o GitHub:

```text
.env
API Keys
tokens
credenciais
cookies
senhas
arquivos de autenticação
bancos de dados pessoais
```

Antes de qualquer commit:

```bash
git status
```

Confira exatamente quais arquivos serão enviados.

---

# 📂 Boas práticas

Recomendado:

```text
JARVIS
├── core
├── nexus
├── plugins
├── integrations
├── services
├── config
├── tests
├── scripts
├── docs
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
└── main.py
```

---

# 🚀 Roadmap

Algumas possíveis evoluções do projeto:

- [ ] instalador automático;
- [ ] atualização automática;
- [ ] interface gráfica renovada;
- [ ] site oficial de download;
- [ ] pacote `.deb`;
- [ ] AppImage;
- [ ] gerenciamento visual das APIs;
- [ ] painel do NEXUS;
- [ ] histórico das decisões do orquestrador;
- [ ] controle de consumo de tokens;
- [ ] fallback automático entre IAs;
- [ ] gerenciamento visual de plugins;
- [ ] sistema de permissões;
- [ ] sandbox para comandos;
- [ ] modo offline;
- [ ] sistema de memória melhorado;
- [ ] inicialização automática com Linux;
- [ ] instalador de um comando.

---

# 🌐 Site de download

Uma evolução planejada é disponibilizar um site próprio do JARVIS destinado principalmente a:

- download;
- versões disponíveis;
- changelog;
- instruções de instalação;
- documentação;
- requisitos;
- atualizações.

---

# 🖥️ Interface

A interface do JARVIS poderá evoluir independentemente do núcleo do assistente.

Isso permite atualizar:

```text
Frontend
```

sem precisar modificar completamente:

```text
Core
NEXUS
Plugins
Integrações
```

---

# 🧪 Desenvolvimento

Crie uma branch:

```bash
git checkout -b feature/nome-da-funcionalidade
```

Depois:

```bash
git add .
git commit -m "feat: adiciona nova funcionalidade"
git push origin feature/nome-da-funcionalidade
```

---

# 🤝 Contribuições

Contribuições devem preferencialmente:

1. manter a arquitetura modular;
2. não expor credenciais;
3. incluir tratamento de erros;
4. não adicionar chamadas de IA desnecessárias;
5. preservar compatibilidade com Linux;
6. evitar dependências desnecessárias;
7. documentar novas variáveis de ambiente.

---

# 📜 Licença

Defina uma licença antes de distribuir o software publicamente.

Algumas opções comuns:

```text
MIT
Apache-2.0
GPL-3.0
Proprietária
```

Se o objetivo for manter determinadas partes fechadas ou controlar distribuição comercial, revise a licença antes de liberar versões públicas.

---

# 👨‍💻 Autor

Projeto JARVIS

GitHub:

https://github.com/limazk/JARVIS

---

# ⚡ JARVIS

> Um núcleo. Várias inteligências. A ferramenta certa para cada tarefa.

```text
JARVIS
  │
  ├── entende
  ├── decide
  ├── executa
  └── aprende com a arquitetura
```

---

**O projeto está em desenvolvimento contínuo e funcionalidades podem mudar entre versões.**
