"""
Dados de status compartilhados entre as duas interfaces gráficas do
Jarvis (a antiga, em CustomTkinter — `interface/app.py` — e a nova,
em pywebview — `interface_web/`).

Extraído de dentro de `interface/app.py`/`DashboardPanel`/`ActivityPanel`
pra não duplicar a mesma lógica duas vezes: as duas interfaces mostram
exatamente os mesmos números reais (CPU/RAM/disco, rede, processos,
status dos módulos, atividade recente) — só o desenho na tela muda.
Nenhuma das duas depende de nenhuma biblioteca de UI (nem tkinter, nem
pywebview) — só psutil e os módulos internos do Jarvis — então este
arquivo é testável normalmente, ao contrário das camadas de interface
em si.

Tudo aqui é dado real (psutil/estado do `.env`/banco local) — nunca um
número fabricado só pra "parecer" cheio de informação. Onde a
referência visual do usuário (um painel de diagnóstico de laboratório,
estilo ficção científica) mostra algo que o Jarvis não tem de verdade
(GPU/NPU, por exemplo), a métrica correspondente simplesmente não
existe aqui — melhor não mostrar do que inventar.
"""
from __future__ import annotations

import platform
import threading
import time
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.agent import JarvisAgent

# Estado entre chamadas pra calcular taxas (bytes/s) a partir dos
# contadores cumulativos do psutil — protegido por lock porque
# get_stats() pode ser chamado de threads diferentes (ex.: o polling da
# interface web roda numa thread do pywebview).
_net_lock = threading.Lock()
_last_net_sample: dict | None = None

# Processos reaproveitados entre chamadas: psutil.Process.cpu_percent()
# só devolve um número útil quando chamado DUAS vezes no mesmo objeto
# com um tempo entre as chamadas — um Process novo a cada poll sempre
# devolveria 0%. Guardamos os objetos (não os números) de uma chamada
# pra outra; nunca cresce sem limite porque é reconstruído do zero a
# cada get_top_processes() a partir dos PIDs vivos no momento.
_process_lock = threading.Lock()
_process_cache: dict[int, object] = {}

# Varrer TODOS os processos do sistema (nome/CPU/RAM/status, um por um)
# é caro — num Windows real com 200-300 processos abertos, isso sozinho
# já pode levar centenas de ms. A interface só pede um "top 6" pra
# preencher um painel visual, não precisa desse dado atualizado a cada
# segundo — por isso o resultado fica em cache por alguns segundos
# (_PROCESS_CACHE_TTL) e só faz a varredura de verdade quando esse prazo
# vence. Foi essa varredura completa rodando a cada poll de 1s (junto
# com o resto do get_snapshot()) que deixava a interface pesada/lenta.
_PROCESS_CACHE_TTL = 4.0
_process_cache_time: float | None = None
_process_cache_result: list[dict] = []


def get_stats() -> dict:
    """
    CPU/RAM/disco/rede (%, GB e KB/s) e a hora atual. Nunca levanta
    exceção: se o psutil falhar por algum motivo (ambiente exótico,
    permissão), devolve `None` nos campos que não deu pra ler em vez
    de derrubar a tela toda por causa de um número de diagnóstico.
    """
    cpu = ram = disco = None
    ram_used_gb = ram_total_gb = None
    disco_used_gb = disco_total_gb = None
    net_sent_kbps = net_recv_kbps = None

    try:
        import psutil

        cpu = psutil.cpu_percent(interval=None)

        mem = psutil.virtual_memory()
        ram = mem.percent
        ram_used_gb = round((mem.total - mem.available) / (1024 ** 3), 1)
        ram_total_gb = round(mem.total / (1024 ** 3), 1)

        disk_path = "C:\\" if platform.system() == "Windows" else "/"
        disk = psutil.disk_usage(disk_path)
        disco = disk.percent
        disco_used_gb = round(disk.used / (1024 ** 3), 1)
        disco_total_gb = round(disk.total / (1024 ** 3), 1)

        net_sent_kbps, net_recv_kbps = _net_rate_kbps(psutil)
    except Exception:
        pass

    return {
        "cpu": cpu,
        "ram": ram,
        "ram_used_gb": ram_used_gb,
        "ram_total_gb": ram_total_gb,
        "disco": disco,
        "disco_used_gb": disco_used_gb,
        "disco_total_gb": disco_total_gb,
        "net_sent_kbps": net_sent_kbps,
        "net_recv_kbps": net_recv_kbps,
        "hora": datetime.now().strftime("%H:%M"),
    }


def _net_rate_kbps(psutil_module) -> tuple[float | None, float | None]:
    """
    Taxa de rede (KB/s, enviado/recebido) a partir da diferença entre
    dois contadores cumulativos do psutil — só existe a partir da
    SEGUNDA chamada (a primeira só guarda a amostra e devolve `None`,
    já que uma taxa precisa de dois pontos no tempo).
    """
    global _last_net_sample

    counters = psutil_module.net_io_counters()
    now = time.monotonic()

    with _net_lock:
        previous = _last_net_sample
        _last_net_sample = {"time": now, "sent": counters.bytes_sent, "recv": counters.bytes_recv}

    if previous is None:
        return None, None

    elapsed = now - previous["time"]
    if elapsed <= 0:
        return None, None

    sent_kbps = max(0.0, (counters.bytes_sent - previous["sent"]) / 1024 / elapsed)
    recv_kbps = max(0.0, (counters.bytes_recv - previous["recv"]) / 1024 / elapsed)
    return round(sent_kbps, 1), round(recv_kbps, 1)


def get_top_processes(limit: int = 6) -> list[dict]:
    """
    Processos reais de maior uso de CPU no momento (nome, %CPU, %RAM),
    igual um gerenciador de tarefas simplificado — o "PROCESS ACTIVITY"
    da referência visual do usuário, mas com processos de verdade do
    computador em vez de nomes inventados. Nunca levanta exceção: uma
    falha de permissão num processo específico só pula ele; uma falha
    geral do psutil devolve lista vazia.

    A varredura de todos os processos só roda de verdade a cada
    `_PROCESS_CACHE_TTL` segundos (ver comentário do cache acima); entre
    uma varredura e outra devolve o resultado guardado, recortado pro
    `limit` pedido — então mesmo chamando isso a cada 1s (o polling da
    interface), o custo pesado só acontece a cada poucos segundos.
    """
    global _process_cache_time, _process_cache_result

    try:
        import psutil
    except Exception:
        return []

    now = time.monotonic()
    with _process_lock:
        if _process_cache_time is not None and (now - _process_cache_time) < _PROCESS_CACHE_TTL:
            return list(_process_cache_result[:limit])

        alive_pids = set()
        try:
            alive_pids = set(psutil.pids())
        except Exception:
            return list(_process_cache_result[:limit])

        # Descarta processos que já encerraram desde a última varredura.
        for pid in list(_process_cache):
            if pid not in alive_pids:
                del _process_cache[pid]

        rows: list[dict] = []
        for pid in alive_pids:
            proc = _process_cache.get(pid)
            if proc is None:
                try:
                    proc = psutil.Process(pid)
                    proc.cpu_percent(interval=None)  # "aquece" a medição (ver docstring do módulo)
                except Exception:
                    continue
                _process_cache[pid] = proc

            try:
                name = proc.name()
                cpu = proc.cpu_percent(interval=None)
                mem = proc.memory_percent()
                status = proc.status()
            except Exception:
                continue

            rows.append({"name": name, "cpu": round(cpu, 1), "mem": round(mem, 1), "status": status})

        rows.sort(key=lambda r: (r["cpu"], r["mem"]), reverse=True)
        _process_cache_result = rows
        _process_cache_time = now
        return list(rows[:limit])


def get_module_rows(agent: "JarvisAgent") -> list[dict]:
    """
    As nove linhas de status de módulo da "Visão geral" (IA, voz de
    entrada/saída, voz contínua, memória, Spotify, Discord, GitHub,
    Google) — refletindo o `.env`/estado atual de verdade, nunca
    valores fixos/fabricados. Recebe o `JarvisAgent` já criado (pra
    saber se o provedor de IA está mesmo disponível) em vez de criar
    um novo — quem chama já tem um.

    Cada linha: {"label": str, "detail": str, "ok": bool, "category":
    "core" | "integration"} — a categoria só existe pra interface poder
    separar visualmente "o que faz o Jarvis funcionar" de "o que ele
    conecta no mundo de fora" (duas seções na "Visão geral", igual a
    referência visual do usuário separa "System Health" de "Module
    Status"); nenhuma das duas interfaces é obrigada a usar isso.
    """
    from config.settings import settings
    from voice.listener import listener

    rows: list[dict] = []

    llm_ok = agent.llm.available
    llm_detail = settings.llm_provider.capitalize()
    if settings.llm_auto_fallback:
        llm_detail += " (+ fallback automático)"
    if not llm_ok:
        llm_detail += " — indisponível"
    rows.append({"label": "Inteligência (IA)", "detail": llm_detail, "ok": llm_ok, "category": "core"})

    mic_ok = listener.is_ready()
    rows.append({
        "label": "Voz de entrada",
        "detail": "Microfone pronto" if mic_ok else "Microfone indisponível",
        "ok": mic_ok,
        "category": "core",
    })

    rows.append({"label": "Voz de saída", "detail": settings.tts_provider.capitalize(), "ok": True, "category": "core"})

    rows.append({
        "label": "Voz contínua",
        "detail": f'Ligada ("{settings.wake_word}")' if settings.wake_word_enabled else "Desligada",
        "ok": settings.wake_word_enabled,
        "category": "core",
    })

    rows.append({"label": "Memória", "detail": "Banco local ativo", "ok": True, "category": "core"})

    spotify_ok = bool(settings.spotify_client_id and settings.spotify_client_secret)
    spotify_connected = (settings.base_dir / ".spotify_cache").exists()
    spotify_detail = "Conectado" if spotify_connected else ("Configurado" if spotify_ok else "Não configurado")
    rows.append({"label": "Spotify", "detail": spotify_detail, "ok": spotify_ok, "category": "integration"})

    discord_ok = bool(settings.discord_bot_token)
    rows.append({
        "label": "Bot do Discord",
        "detail": "Configurado (rode --discord)" if discord_ok else "Não configurado",
        "ok": discord_ok,
        "category": "integration",
    })

    github_ok = bool(settings.github_token)
    rows.append({"label": "GitHub", "detail": "Configurado" if github_ok else "Não configurado", "ok": github_ok, "category": "integration"})

    google_ok = (settings.base_dir / "google_credentials.json").exists()
    google_connected = (settings.base_dir / "google_token.json").exists()
    google_detail = "Conectado" if google_connected else ("Configurado" if google_ok else "Não configurado")
    rows.append({"label": "Google (Gmail/Calendar/Drive)", "detail": google_detail, "ok": google_ok, "category": "integration"})

    return rows


def get_activity_rows(limit: int = 30) -> list[dict]:
    """
    Últimas atividades registradas (memory/database.py::recent_activities),
    já convertidas pra um formato simples ({"time": "HH:MM", "description":
    str}) e na ordem certa pra exibir (mais antiga primeiro, mais nova por
    último) — mesma ordem que o `ActivityPanel` do CustomTkinter sempre
    usou. Nunca levanta exceção: um banco ainda não inicializado ou uma
    falha de leitura vira lista vazia em vez de travar a tela.
    """
    try:
        from memory.database import recent_activities

        rows = recent_activities(limit=limit)
    except Exception:
        return []

    result: list[dict] = []
    for row in reversed(rows):
        try:
            ts = datetime.fromisoformat(row["created_at"]).strftime("%H:%M")
        except Exception:
            ts = "--:--"
        result.append({"time": ts, "description": row["description"]})
    return result
