"""
Configurações centrais do Jarvis.

Tudo que pode variar entre máquinas ou é sensível (chaves de API)
fica no arquivo .env (nunca no código-fonte). Este módulo lê o
.env, aplica valores padrão sensatos e expõe um único objeto
`settings` para o resto do sistema importar.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field, fields
from pathlib import Path

from dotenv import load_dotenv

def _compute_base_dir() -> Path:
    """
    Raiz do projeto (pasta que contém main.py) — ou, quando empacotado
    como .exe pelo PyInstaller (sys.frozen), a pasta onde o .exe
    realmente está. Isso importa porque, dentro de um .exe "onefile",
    __file__ aponta pra uma pasta TEMPORÁRIA que o Windows apaga ao
    fechar o programa — se usássemos ela, o .env, o banco de dados e os
    logs "desapareceriam" a cada execução.

    Função separada (em vez de só código solto no topo do módulo) pra
    poder ser testada isoladamente, sem precisar de `importlib.reload`
    no módulo inteiro — isso evitaria criar um segundo objeto `settings`
    dessincronizado do resto do sistema.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = _compute_base_dir()

# Carrega o .env da raiz do projeto (ou da pasta do .exe), se existir.
load_dotenv(BASE_DIR / ".env")


def _bool(env_name: str, default: bool) -> bool:
    val = os.getenv(env_name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "sim", "on"}


def _str(env_name: str, default: str) -> str:
    return os.getenv(env_name, default)


def _int(env_name: str, default: int) -> int:
    val = os.getenv(env_name)
    if val is None:
        return default
    try:
        return int(val.strip())
    except ValueError:
        return default


def _float(env_name: str, default: float) -> float:
    val = os.getenv(env_name)
    if val is None:
        return default
    try:
        return float(val.strip())
    except ValueError:
        return default


@dataclass
class Settings:
    # Identidade
    jarvis_name: str = field(default_factory=lambda: _str("JARVIS_NAME", "Jarvis"))
    language: str = field(default_factory=lambda: _str("LANGUAGE", "pt-BR"))
    # Como o Jarvis se dirige ao usuário (ex.: "Senhor"). Vazio ("") desliga
    # esse comportamento e o Jarvis volta a falar sem forma de tratamento.
    user_title: str = field(default_factory=lambda: _str("USER_TITLE", "Senhor"))

    # Comportamento
    debug: bool = field(default_factory=lambda: _bool("DEBUG", False))
    voice_enabled: bool = field(default_factory=lambda: _bool("VOICE_ENABLED", True))
    wake_word_enabled: bool = field(default_factory=lambda: _bool("WAKE_WORD_ENABLED", True))
    wake_word: str = field(default_factory=lambda: _str("WAKE_WORD", "jarvis"))
    wake_word_model: str = field(default_factory=lambda: _str("WAKE_WORD_MODEL", "hey_jarvis"))
    # Frase que o Jarvis fala assim que ouve a wake word, antes de escutar o
    # comando de verdade (ex.: "Jarvis" -> "Sim, Senhor. O que deseja?").
    # Vazia ("") = o Jarvis monta a frase sozinho a partir de USER_TITLE.
    wake_greeting: str = field(default_factory=lambda: _str("WAKE_GREETING", ""))
    allow_critical_actions: bool = field(default_factory=lambda: _bool("ALLOW_CRITICAL_ACTIONS", False))

    # LLM
    llm_provider: str = field(default_factory=lambda: _str("LLM_PROVIDER", "local"))
    anthropic_api_key: str = field(default_factory=lambda: _str("ANTHROPIC_API_KEY", ""))
    claude_model: str = field(default_factory=lambda: _str("CLAUDE_MODEL", "claude-sonnet-4-5"))
    openai_api_key: str = field(default_factory=lambda: _str("OPENAI_API_KEY", ""))
    openai_model: str = field(default_factory=lambda: _str("OPENAI_MODEL", "gpt-4o-mini"))
    # Gemini e Groq: camadas gratuitas sem cartão de crédito (seção "IAs grátis" do README).
    gemini_api_key: str = field(default_factory=lambda: _str("GEMINI_API_KEY", ""))
    gemini_model: str = field(default_factory=lambda: _str("GEMINI_MODEL", "gemini-3.6-flash"))
    groq_api_key: str = field(default_factory=lambda: _str("GROQ_API_KEY", ""))
    # llama-3.3-70b-versatile foi descontinuado pela Groq em 16/08/2026 —
    # openai/gpt-oss-120b é o substituto recomendado por eles (também com
    # suporte a tool-calling).
    groq_model: str = field(default_factory=lambda: _str("GROQ_MODEL", "openai/gpt-oss-120b"))
    local_llm_url: str = field(default_factory=lambda: _str("LOCAL_LLM_URL", "http://127.0.0.1:11434"))
    local_llm_model: str = field(default_factory=lambda: _str("LOCAL_LLM_MODEL", "qwen3.5:9b"))
    local_llm_context: int = field(default_factory=lambda: _int("LOCAL_LLM_CONTEXT", 8192))
    local_llm_temperature: float = field(default_factory=lambda: _float("LOCAL_LLM_TEMPERATURE", 0.6))
    local_llm_thinking: bool = field(default_factory=lambda: _bool("LOCAL_LLM_THINKING", False))
    # Modelos locais (Ollama) rodando em CPU podem demorar bem mais que os
    # provedores em nuvem pra gerar a primeira resposta, especialmente em
    # modelos maiores (ex.: qwen2.5:14b) ou na primeira chamada depois de
    # abrir o Jarvis (o Ollama carrega o modelo pra RAM/VRAM nessa hora).
    # 60s era curto demais pra isso e gerava falsos "modelo indisponível".
    local_llm_timeout: int = field(default_factory=lambda: _int("LOCAL_LLM_TIMEOUT", 180))
    # O Ollama descarrega o modelo da RAM/VRAM 5 minutos depois do último uso
    # (comportamento padrão dele). Isso faz o Jarvis parecer "lento" mesmo com
    # o Ollama funcionando bem: toda vez que passa mais de 5min entre
    # mensagens, a próxima resposta paga o custo de recarregar o modelo
    # inteiro do disco antes de gerar qualquer texto. Mandando "keep_alive"
    # maior em cada requisição, o Ollama mantém o modelo carregado por mais
    # tempo entre usos do Jarvis.
    ollama_keep_alive: str = field(default_factory=lambda: _str("OLLAMA_KEEP_ALIVE", "15m"))
    # Se o provedor escolhido (LLM_PROVIDER) falhar ou não estiver configurado,
    # cai sozinho pros gratuitos (Gemini -> Groq -> Ollama local) — core/brain.py.
    llm_auto_fallback: bool = field(default_factory=lambda: _bool("LLM_AUTO_FALLBACK", True))

    # Voz
    stt_provider: str = field(default_factory=lambda: _str("STT_PROVIDER", "google"))
    tts_provider: str = field(default_factory=lambda: _str("TTS_PROVIDER", "edge"))
    edge_tts_voice: str = field(default_factory=lambda: _str("EDGE_TTS_VOICE", "pt-BR-AntonioNeural"))
    elevenlabs_api_key: str = field(default_factory=lambda: _str("ELEVENLABS_API_KEY", ""))
    elevenlabs_voice_id: str = field(default_factory=lambda: _str("ELEVENLABS_VOICE_ID", ""))

    # Integrações externas opcionais
    openweather_api_key: str = field(default_factory=lambda: _str("OPENWEATHER_API_KEY", ""))
    weather_city: str = field(default_factory=lambda: _str("WEATHER_CITY", "Brasilia,BR"))
    github_token: str = field(default_factory=lambda: _str("GITHUB_TOKEN", ""))
    github_username: str = field(default_factory=lambda: _str("GITHUB_USERNAME", ""))
    # Controle de reprodução do Spotify (tools/spotify.py) — app grátis em
    # https://developer.spotify.com/dashboard. Requer conta Premium para
    # tocar/pausar/pular/volume (consultar o que está tocando funciona no plano grátis).
    spotify_client_id: str = field(default_factory=lambda: _str("SPOTIFY_CLIENT_ID", ""))
    spotify_client_secret: str = field(default_factory=lambda: _str("SPOTIFY_CLIENT_SECRET", ""))
    spotify_redirect_uri: str = field(
        default_factory=lambda: _str("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")
    )
    # Vendas/cobranças via Mercado Pago (tools/mercadopago.py) — token grátis em
    # https://www.mercadopago.com.br/developers/panel ("Suas integrações" > Credenciais).
    mercadopago_access_token: str = field(default_factory=lambda: _str("MERCADOPAGO_ACCESS_TOKEN", ""))
    # Bot do Discord (interface/discord_bot.py) — outra forma de conversar com
    # o Jarvis de fora do PC (ex.: do celular, por DM). DISCORD_OWNER_ID é o ID
    # numérico da SUA conta — o bot ignora qualquer outra pessoa por segurança.
    discord_bot_token: str = field(default_factory=lambda: _str("DISCORD_BOT_TOKEN", ""))
    discord_owner_id: str = field(default_factory=lambda: _str("DISCORD_OWNER_ID", ""))

    # Integração local com o projeto ROTINA. A chave nunca é registrada em logs.
    rotina_enabled: bool = field(default_factory=lambda: _bool("ROTINA_ENABLED", True))
    rotina_url: str = field(default_factory=lambda: _str("ROTINA_URL", "http://127.0.0.1:8765"))
    rotina_key: str = field(default_factory=lambda: _str("ROTINA_KEY", ""))
    rotina_dir: str = field(default_factory=lambda: _str("ROTINA_DIR", ""))
    rotina_auto_start: bool = field(default_factory=lambda: _bool("ROTINA_AUTO_START", True))
    rotina_stop_on_exit: bool = field(default_factory=lambda: _bool("ROTINA_STOP_ON_EXIT", False))
    fast_cache_enabled: bool = field(default_factory=lambda: _bool("FAST_CACHE_ENABLED", True))
    fast_cache_ttl: int = field(default_factory=lambda: _int("FAST_CACHE_TTL", 15))

    # Caminhos
    base_dir: Path = BASE_DIR
    db_path: Path = field(default_factory=lambda: BASE_DIR / "database" / "jarvis.db")
    log_path: Path = field(default_factory=lambda: BASE_DIR / "logs" / "jarvis.log")
    apps_json_path: Path = field(default_factory=lambda: BASE_DIR / "config" / "apps.json")
    personality_path: Path = field(default_factory=lambda: BASE_DIR / "config" / "personality.json")
    instance_lock_path: Path = field(default_factory=lambda: BASE_DIR / "logs" / "jarvis.lock")
    screenshots_dir: Path = field(
        default_factory=lambda: Path.home() / "Pictures" / "Jarvis" / "Screenshots"
    )

    def validate(self) -> list[str]:
        """Retorna uma lista de avisos. Nunca impede o Jarvis de iniciar."""
        warnings: list[str] = []
        if self.llm_provider == "claude" and not self.anthropic_api_key:
            warnings.append(
                "ANTHROPIC_API_KEY não definida — o Jarvis vai funcionar apenas "
                "com comandos locais (sem interpretação avançada por IA)."
            )
        if self.llm_provider == "openai" and not self.openai_api_key:
            warnings.append("OPENAI_API_KEY não definida.")
        if self.llm_provider == "gemini" and not self.gemini_api_key:
            warnings.append(
                "GEMINI_API_KEY não definida — gere uma grátis (sem cartão) em "
                "https://aistudio.google.com/apikey."
            )
        if self.llm_provider == "groq" and not self.groq_api_key:
            warnings.append(
                "GROQ_API_KEY não definida — gere uma grátis (sem cartão) em "
                "https://console.groq.com/keys."
            )
        if self.llm_provider == "local":
            # Estado detalhado fica no doctor/LocalProvider.health_check; aqui só
            # deixamos uma orientação estática que não faz I/O na inicialização.
            if not self.local_llm_model:
                warnings.append("LOCAL_LLM_MODEL não definido.")
        if self.rotina_enabled and not self.rotina_key:
            warnings.append("ROTINA_KEY não definida — a API ROTINA poderá responder 401.")
        if self.tts_provider == "elevenlabs" and not self.elevenlabs_api_key:
            warnings.append("ELEVENLABS_API_KEY não definida — TTS vai cair para Edge TTS.")
        return warnings


settings = Settings()


def save_env_values(values: dict[str, str]) -> None:
    """
    Cria (se não existir) ou atualiza o `.env` do projeto com os pares
    chave=valor recebidos, preservando o resto do conteúdo/comentários.

    Existe pra que a interface gráfica (tela de configuração inicial,
    parte da preparação do Jarvis para rodar como .exe) possa salvar a
    chave de API escolhida sem exigir que a pessoa edite o `.env` na mão
    num editor de texto — mas continua sendo o MESMO arquivo `.env` de
    sempre, então nada muda pra quem preferir editar manualmente.
    """
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        example_path = BASE_DIR / ".env.example"
        base_content = example_path.read_text(encoding="utf-8") if example_path.exists() else ""
        env_path.write_text(base_content, encoding="utf-8")

    lines = env_path.read_text(encoding="utf-8").splitlines()
    remaining = dict(values)
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in remaining:
                new_lines.append(f"{key}={remaining.pop(key)}")
                continue
        new_lines.append(line)
    for key, value in remaining.items():
        new_lines.append(f"{key}={value}")

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def reload_settings() -> None:
    """
    Relê o `.env` do zero e atualiza o objeto `settings` (o mesmo objeto
    que o resto do sistema já importou) em memória, sem precisar
    reiniciar o processo — usado depois de `save_env_values` pela tela
    de configuração da interface gráfica.
    """
    load_dotenv(BASE_DIR / ".env", override=True)
    fresh = Settings()
    for f in fields(fresh):
        setattr(settings, f.name, getattr(fresh, f.name))
