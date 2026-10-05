"""
Subagentes especializados — seção 49 do spec.

Para este protótipo, "múltiplos agentes" não significa múltiplas
chamadas de API (isso custaria tempo e dinheiro à toa, e destruiria a
resposta quase instantânea que o Jarvis tem hoje). Em vez disso, o
Jarvis escolhe internamente, por palavras-chave, qual "especialista"
combina mais com o pedido, e aplica três coisas nele — tudo isso
ainda dentro de UMA ÚNICA chamada ao LLM, exatamente como a seção 49
permite para o MVP ("poderá funcionar internamente sem múltiplas
chamadas desnecessárias à API"):

1. `extra_prompt` — uma instrução curta de personalidade/foco, como
   já existia.
2. `preferred_tools` — os nomes das ferramentas mais relevantes pra
   esse assunto, que passam a aparecer PRIMEIRO na lista de tools
   mandada pro LLM (core/router.py usa isso via
   ToolRegistry.as_llm_tool_schemas(prioritize=...)). Nenhuma
   ferramenta é removida — o Jarvis nunca perde capacidade —, só
   reordenada, o que ajuda o modelo a notar mais rápido a ferramenta
   certa sem custar nada a mais.
3. `context_builder` — uma função opcional, sem argumentos, que
   devolve uma linha de contexto REAL e barato (dado que o Jarvis já
   tem local, sem chamar nenhuma API externa) pra colar no prompt.
   Ex.: o especialista de Sistema já manda o CPU/RAM/disco atuais
   direto no prompt, então perguntas simples ("como tá minha RAM?")
   podem ser respondidas sem nem precisar chamar a tool
   `system_status` — economiza uma ida e volta inteira. Nunca pode
   levantar exceção nem demorar (só lê psutil/SQLite locais, os
   mesmos que a interface gráfica já usa); qualquer falha vira string
   vazia e é ignorada silenciosamente pelo router.

Se nenhum especialista bater com confiança, o Jarvis usa o prompt
genérico normal (core/router.SYSTEM_PROMPT) e a lista de tools na
ordem padrão — a especialização só entra quando faz sentido.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class Specialist:
    name: str
    keywords: tuple[str, ...]
    extra_prompt: str
    # Nomes de tools (ver tools/registry.py) priorizadas na lista mandada
    # ao LLM — só reordena, nunca restringe de verdade (o Jarvis sempre
    # pode usar qualquer ferramenta, mesmo fora do "assunto" detectado).
    preferred_tools: tuple[str, ...] = field(default_factory=tuple)
    # Função sem argumentos que devolve uma linha de contexto real e
    # local pra colar no prompt (ou "" se não tiver nada útil agora).
    context_builder: Optional[Callable[[], str]] = None


def _system_context() -> str:
    """
    CPU/RAM/disco reais agora mesmo — os mesmos números que o painel
    "Monitor de desempenho" da interface mostra (interface/status_info.py),
    reaproveitados aqui pra o especialista de Sistema já poder responder
    perguntas simples ("como tá minha RAM?") sem precisar chamar a tool
    `system_status` só pra descobrir o óbvio.
    """
    from interface.status_info import get_stats

    stats = get_stats()
    partes = []
    if stats.get("cpu") is not None:
        partes.append(f"CPU em {stats['cpu']:.0f}%")
    if stats.get("ram") is not None:
        partes.append(f"RAM em {stats['ram']:.0f}% ({stats['ram_used_gb']}/{stats['ram_total_gb']} GB)")
    if stats.get("disco") is not None:
        partes.append(f"disco em {stats['disco']:.0f}% ({stats['disco_used_gb']}/{stats['disco_total_gb']} GB)")
    if not partes:
        return ""
    return "Estado real do sistema agora: " + ", ".join(partes) + "."


def _productivity_context() -> str:
    """
    Quantidade real de lembretes pendentes (mesma tabela que
    tools/reminders.py::list_reminders usa) — dá ao especialista de
    Produtividade uma noção imediata da agenda do usuário sem precisar
    chamar `list_reminders` só pra saber se tem algo pendente ou não.
    """
    try:
        from memory.database import get_connection

        with get_connection() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM reminders WHERE status = 'pending'").fetchone()
        n = row["n"] if row else 0
    except Exception:
        return ""

    if n == 0:
        return "O usuário não tem nenhum lembrete pendente no momento."
    plural = "lembrete pendente" if n == 1 else "lembretes pendentes"
    return f"O usuário tem {n} {plural} no momento."


SPECIALISTS: tuple[Specialist, ...] = (
    Specialist(
        name="JarvisDeveloper",
        keywords=(
            "código", "codigo", "bug", "erro", "função", "funcao", "programa", "programação",
            "programacao", "python", "javascript", "compila", "debug", "instala", "dependência",
            "dependencia", "git", "github", "repositório", "repositorio", "terminal", "script",
        ),
        extra_prompt=(
            "Modo especialista: Programação. Priorize ferramentas de terminal, git e arquivos "
            "de projeto. Seja técnico e preciso; sugira comandos concretos quando fizer sentido."
        ),
        preferred_tools=(
            "run_shell_command", "git_status", "git_push", "create_issue", "list_my_repos",
            "repo_info", "open_github", "find_file", "open_folder",
        ),
    ),
    Specialist(
        name="JarvisResearcher",
        keywords=(
            "pesquisa", "pesquise", "notícia", "noticia", "o que é", "o que e", "quem foi",
            "quem é", "explica", "explique", "resumo", "resuma", "artigo", "significado",
        ),
        extra_prompt=(
            "Modo especialista: Pesquisa. Priorize a ferramenta de busca na internet para "
            "informações atuais; sempre que usar um resultado de busca, mencione a fonte."
        ),
        preferred_tools=("web_search", "open_browser_search", "read_screen_text", "get_weather"),
    ),
    Specialist(
        name="JarvisSystem",
        keywords=(
            "cpu", "ram", "memória", "memoria", "processador", "bateria", "volume", "wifi",
            "wi-fi", "bloqueia", "trava", "processos", "disco", "desliga", "reinicia",
        ),
        extra_prompt="Modo especialista: Sistema. Priorize as ferramentas de monitoramento e controle do Windows.",
        preferred_tools=("system_status", "disk_space", "set_volume", "mute_volume", "lock_computer"),
        context_builder=_system_context,
    ),
    Specialist(
        name="JarvisProductivity",
        keywords=(
            "lembrete", "lembra", "nota", "anota", "agenda", "tarefa", "timer", "cronômetro",
            "cronometro", "compromisso",
        ),
        extra_prompt="Modo especialista: Produtividade. Priorize notas, lembretes e timers.",
        preferred_tools=(
            "add_reminder", "list_reminders", "add_note", "list_notes", "remove_note",
            "start_timer", "create_calendar_event", "list_upcoming_events", "morning_briefing",
        ),
        context_builder=_productivity_context,
    ),
    Specialist(
        name="JarvisFiles",
        keywords=(
            "arquivo", "pasta", "documento", "download", "procura", "espaço", "espaco",
            "print", "captura", "screenshot",
        ),
        extra_prompt="Modo especialista: Arquivos. Priorize as ferramentas de arquivos, pastas e capturas de tela.",
        preferred_tools=("find_file", "create_folder", "open_folder", "take_screenshot", "disk_space", "search_drive_files"),
    ),
    Specialist(
        name="JarvisBusiness",
        keywords=(
            "venda", "vendas", "mercado pago", "mercadopago", "cobrança", "cobranca",
            "cobranças", "cobrancas", "pagamento", "pagamentos", "recebi", "recebimento",
            "saldo", "fatura", "cliente pagou",
        ),
        extra_prompt=(
            "Modo especialista: Negócios/Mercado Pago. Priorize as ferramentas de vendas, "
            "cobranças e saldo do Mercado Pago; seja direto com valores e datas, e nunca "
            "invente um número — se a ferramenta não trouxer o dado, diga isso claramente."
        ),
        preferred_tools=("mercadopago_vendas_recentes", "mercadopago_criar_cobranca", "mercadopago_saldo"),
    ),
)


def pick_specialist(text: str) -> Specialist | None:
    normalized = text.lower()
    best: Specialist | None = None
    best_score = 0
    for specialist in SPECIALISTS:
        score = sum(1 for kw in specialist.keywords if kw in normalized)
        if score > best_score:
            best, best_score = specialist, score
    return best
