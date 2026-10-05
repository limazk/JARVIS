"""
Parser de intenção local (sem LLM) — seção 40 do spec ("modo sem IA").

Comandos simples e frequentes não precisam passar pela API do LLM.
Isso reduz latência, custo, e funciona offline. Se nada aqui bater,
o router cai para o cérebro (LLM) com tool-calling — só nesse caso
a interpretação avançada entra em ação.

ORDEM IMPORTA: regras mais específicas ficam antes de regras
genéricas (ex.: "abre downloads" precisa ser checada antes da regra
genérica "abre X" -> open_application).

Para adicionar um novo comando local: crie uma IntentRule com um
regex e o nome da tool que ele deve acionar.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Callable, Optional

Extractor = Callable[["re.Match[str]"], dict]


@dataclass
class IntentRule:
    pattern: "re.Pattern[str]"
    tool_name: str
    extractor: Extractor = field(default=lambda m: {})


@dataclass
class IntentMatch:
    matched: bool
    tool_name: Optional[str] = None
    params: dict = field(default_factory=dict)


def _group(name: str, key: str | None = None) -> Extractor:
    return lambda m: {(key or name): m.group(name).strip()}


def _volume_level(m: "re.Match[str]") -> dict:
    return {"level": int(m.group("level"))}


def _query_and_playlist(m: "re.Match[str]") -> dict:
    return {"query": m.group("query").strip(), "playlist": m.group("playlist").strip()}


def _shuffle_on(_m: "re.Match[str]") -> dict:
    return {"enabled": True}


def _shuffle_off(_m: "re.Match[str]") -> dict:
    return {"enabled": False}


def _weather_day(m: "re.Match[str]") -> dict:
    text = m.group(0)
    day = "amanhã" if re.search(r"amanh[ãa]", text) else "hoje"
    return {"day": day}


def _money(m: "re.Match[str]") -> dict:
    amount = float(m.group("amount").replace(".", "").replace(",", "."))
    description = (m.groupdict().get("description") or "Movimentação").strip()
    return {"amount": amount, "description": description}


# A ordem importa: regras mais específicas devem vir antes das genéricas.
_RULES: list[IntentRule] = [
    IntentRule(re.compile(r"^(que horas s[aã]o|qual (a )?hora)\b", re.I), "get_time"),

    # --- ROTINA (fonte principal de tarefas e finanças) ---
    IntentRule(re.compile(r"^(quais s[aã]o (as )?minhas tarefas|o que tenho para fazer|o que tenho para (fazer )?hoje|minhas tarefas( de hoje)?|tarefas de hoje|o que tenho hoje)\??$", re.I), "get_today_tasks"),
    IntentRule(re.compile(r"^(qual ([eé] )?minha rotina( hoje)?|como est[aá] minha rotina|o que eu fa[cç]o hoje|qual ([eé] )?minha pr[oó]xima atividade)\??$", re.I), "get_rotina_summary"),
    IntentRule(re.compile(r"^(adiciona|adicione)\s+(?P<title>.+?)\s+(nas|às) tarefas( de hoje)?$", re.I), "add_task", _group("title")),
    IntentRule(re.compile(r"^(marca|marque)\s+(?P<title_or_id>.+?)\s+como conclu[ií]d[ao]$", re.I), "complete_task", _group("title_or_id")),
    IntentRule(re.compile(r"^gastei\s+(?P<amount>[\d.,]+)(\s+reais?)?(\s+com\s+(?P<description>.+))?$", re.I), "add_expense", _money),
    IntentRule(re.compile(r"^(ganhei|recebi)\s+(?P<amount>[\d.,]+)(\s+reais?)?(\s+(com|de)\s+(?P<description>.+))?(\s+hoje)?$", re.I), "add_income", _money),
    IntentRule(re.compile(r"^(quanto (entrou|eu gastei|gastei)( (n)?essa semana)?|como est[aã]o minhas finan[cç]as)\??$", re.I), "get_financial_summary"),
    IntentRule(re.compile(r"^(quanto (meu neg[oó]cio fez|lucrei|faturei|foi o lucro)( (n)?essa semana)?|qual (e )?meu lucro)\??$", re.I), "get_business_summary"),
    IntentRule(re.compile(r"^quanto (eu )?ganhei (n)?essa semana\??$", re.I), "get_weekly_finance"),
    IntentRule(re.compile(r"^como estou comparado (a|à) semana passada\??$", re.I), "compare_weekly_finance"),

    # --- Briefing matinal ("bom dia" -> resumo de clima/agenda/e-mail/
    # lembretes/memória, ver tools/briefing.py) ---
    IntentRule(re.compile(r"^bom dia[,!.]?\s*(jarvis)?[,!.]?$", re.I), "morning_briefing"),
    IntentRule(re.compile(r"^(me (d[aá]|faz)|quero)\s+(um\s+)?(resumo|briefing)( da manh[ãa])?\??$", re.I), "morning_briefing"),

    # --- Sistema / Windows ---
    IntentRule(re.compile(r"^(mute|muta|silencia)", re.I), "mute_volume"),
    IntentRule(
        re.compile(r"^(volume|coloca o volume em|deixa (o volume )?em)\s*(?P<level>\d{1,3})%?$", re.I),
        "set_volume", _volume_level,
    ),
    IntentRule(re.compile(r"^(bloqueia|trava)( o computador| a tela)?$", re.I), "lock_computer"),
    IntentRule(re.compile(r"^tira?\s*(um\s*)?print|^captura de tela", re.I), "take_screenshot"),
    IntentRule(re.compile(r"^(o que est[aá] escrito|leia|le[ia]a o que tem) na tela\??$", re.I), "read_screen_text"),
    IntentRule(re.compile(r"^(como est[aá]|qual (e )?o status d[eo]).*(sistema|computador)|^status do sistema$", re.I), "system_status"),
    IntentRule(re.compile(r"^(quanto|qual).*(ram|mem[oó]ria).*", re.I), "system_status"),
    IntentRule(re.compile(r"^(quanto|qual).*(cpu|processador).*", re.I), "system_status"),
    IntentRule(re.compile(r"^(quanto|qual).*(espa[cç]o|ssd|hd|disco).*", re.I), "disk_space"),

    # --- Calculadora ---
    IntentRule(re.compile(r"^(calcula|calcule|quanto [eé])\s+(?P<expr>.+)$", re.I), "calculate", _group("expr", "expression")),

    # --- Clima ---
    IntentRule(re.compile(r"^(vai chover|qual (a )?(temperatura|previs[aã]o)|previs[aã]o (do tempo)?( para amanh[ãa])?)", re.I), "get_weather", _weather_day),

    # --- Git ---
    IntentRule(re.compile(r"^(qual (o )?status do git|status do git|git status)$", re.I), "git_status"),

    # --- Área de transferência ---
    IntentRule(re.compile(r"^(o que (eu )?copiei|mostra (a )?[aá]rea de transfer[eê]ncia)\??$", re.I), "get_clipboard"),
    IntentRule(re.compile(r"^limpa (a )?[aá]rea de transfer[eê]ncia$", re.I), "clear_clipboard"),

    # --- Memória de longo prazo ---
    IntentRule(re.compile(r"^lembr[ae]\s+que\s+(?P<fact>.+)$", re.I), "remember_fact", _group("fact")),
    IntentRule(re.compile(r"^(o que voc[eê] sabe( sobre mim)?|mostra (o que voc[eê] sabe|minhas mem[oó]rias))\??$", re.I), "list_memories"),

    # --- Notas ---
    IntentRule(re.compile(r"^anota\s+(?P<text>.+)$", re.I), "add_note", _group("text")),
    IntentRule(re.compile(r"^(mostra|quais s[aã]o)( as)?( minhas)? notas$", re.I), "list_notes"),
    IntentRule(re.compile(r"^remove(r)?\s+(a\s+)?nota\s+(?P<text>.+)$", re.I), "remove_note", _group("text")),

    # --- Lembretes ---
    IntentRule(re.compile(r"^quais s[aã]o( os)?( meus)? lembretes\??$", re.I), "list_reminders"),
    IntentRule(re.compile(r"^me lembr[ae]\s+(?P<raw_text>.+)$", re.I), "add_reminder", _group("raw_text")),

    # --- Spotify (controle de reprodução) ---
    IntentRule(re.compile(r"^(pausa|para)\s+(a\s+)?(m[uú]sica|spotify)$", re.I), "spotify_pause"),
    IntentRule(re.compile(r"^(continua|retoma|despausa)\s+(a\s+)?(m[uú]sica|spotify)$", re.I), "spotify_play"),
    IntentRule(re.compile(r"^(pr[oó]xima)\s+(m[uú]sica|faixa)$", re.I), "spotify_next"),
    IntentRule(re.compile(r"^(m[uú]sica|faixa)\s+anterior$", re.I), "spotify_previous"),
    IntentRule(re.compile(r"^volta\s+(a\s+)?m[uú]sica$", re.I), "spotify_previous"),
    IntentRule(
        re.compile(r"^(coloca|deixa)\s+(o\s+)?(volume\s+do\s+spotify\s+em|volume\s+do\s+spotify)\s*(?P<level>\d{1,3})%?$", re.I),
        "spotify_set_volume", _volume_level,
    ),
    IntentRule(re.compile(r"^(o que (est[aá] tocando|t[aá] tocando)|qual (a )?m[uú]sica( est[aá] tocando)?)( no spotify)?\??$", re.I), "spotify_now_playing"),
    IntentRule(
        re.compile(r"^toca\s+(?P<query>.+?)\s+(da|na)\s+(minha\s+)?playlist\s+(?P<playlist>.+)$", re.I),
        "spotify_play", _query_and_playlist,
    ),
    IntentRule(re.compile(r"^toca\s+(a\s+)?(minha\s+)?playlist\s+(?P<name>.+)$", re.I), "spotify_play_playlist", _group("name")),
    IntentRule(re.compile(r"^(mostra|lista|quais s[aã]o)( as)?( minhas)? playlists( do spotify)?\??$", re.I), "spotify_list_playlists"),
    IntentRule(re.compile(r"^(adiciona|coloca|bota)\s+(?P<query>.+?)\s+na fila( do spotify)?$", re.I), "spotify_add_to_queue", _group("query")),
    IntentRule(re.compile(r"^(ativa|liga)\s+(o\s+)?(modo aleat[oó]rio|shuffle)( do spotify)?$", re.I), "spotify_toggle_shuffle", _shuffle_on),
    IntentRule(re.compile(r"^(desativa|desliga)\s+(o\s+)?(modo aleat[oó]rio|shuffle)( do spotify)?$", re.I), "spotify_toggle_shuffle", _shuffle_off),
    IntentRule(re.compile(r"^(curte|favorita|salva)\s+(essa\s+|esta\s+)?(m[uú]sica|faixa)( atual)?( no spotify)?$", re.I), "spotify_save_current_track"),
    IntentRule(re.compile(r"^toca\s+(?P<query>.+)$", re.I), "spotify_play", _group("query")),

    # --- Google (Gmail/Calendar) ---
    IntentRule(re.compile(r"^tenho e-?mail(s)?( novo(s)?| n[aã]o lido(s)?)\??$", re.I), "list_unread_emails"),
    IntentRule(re.compile(r"^(quais? s[aã]o|mostra) (os )?(meus )?e-?mails? n[aã]o lidos?\??$", re.I), "list_unread_emails"),
    IntentRule(re.compile(r"^(que|quais?) compromissos (eu )?tenho (hoje)?\??$", re.I), "list_upcoming_events"),
    IntentRule(re.compile(r"^(minha )?agenda (de )?hoje\??$", re.I), "list_upcoming_events"),

    # --- Timer ---
    IntentRule(re.compile(r"^(cronometra|coloca um timer de|timer de|cronômetro de)\s+(?P<raw_duration>.+)$", re.I), "start_timer", _group("raw_duration")),

    # --- Arquivos ---
    IntentRule(
        re.compile(r"^(abre|abra)\s+(a\s+pasta\s+|minha\s+pasta\s+)?(?P<folder>downloads|documentos|desktop|[aá]rea de trabalho|imagens|v[ií]deos|m[uú]sicas)\s*$", re.I),
        "open_folder", _group("folder"),
    ),
    IntentRule(re.compile(r"^cria(r)?\s+(uma\s+)?pasta\s+(chamada\s+|com o nome\s+)?(?P<name>.+)$", re.I), "create_folder", _group("name")),
    IntentRule(re.compile(r"^procura(r)?\s+(o arquivo\s+)?(?P<name>.+)$", re.I), "find_file", _group("name")),

    # --- Busca / navegador ---
    IntentRule(re.compile(r"^pesquisa[r]?\s+(?P<q>.+)$", re.I), "web_search", _group("q", "query")),
    IntentRule(re.compile(r"^(abre|abra)\s+(o\s+|a\s+)?navegador$", re.I), "open_website", lambda m: {"site": "google"}),

    # --- Abrir programa/site (genérico — fica por último) ---
    IntentRule(re.compile(r"^(abre|abra)\s+(o\s+|a\s+)?(?P<app>[\w\séçãõáéíóúâê]+?)\s*$", re.I), "open_application", _group("app", "app_name")),
]


def match_local_intent(text: str) -> IntentMatch:
    normalized = unicodedata.normalize("NFKC", text).strip().rstrip(".!?")
    normalized = re.sub(r"\s+", " ", normalized)
    for rule in _RULES:
        m = rule.pattern.match(normalized)
        if m:
            return IntentMatch(matched=True, tool_name=rule.tool_name, params=rule.extractor(m))
    return IntentMatch(matched=False)
