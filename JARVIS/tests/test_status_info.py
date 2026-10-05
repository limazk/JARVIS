"""
Testes de interface/status_info.py — a lógica de dados compartilhada
pelas duas interfaces gráficas (CustomTkinter e a nova, em pywebview).
"""
from __future__ import annotations

from unittest.mock import MagicMock

from config.settings import settings
from interface.status_info import get_activity_rows, get_module_rows, get_stats, get_top_processes


def test_get_stats_traz_cpu_ram_disco_rede_e_hora():
    stats = get_stats()

    assert set(stats.keys()) == {
        "cpu", "ram", "ram_used_gb", "ram_total_gb",
        "disco", "disco_used_gb", "disco_total_gb",
        "net_sent_kbps", "net_recv_kbps", "hora",
    }
    # psutil está instalado neste sandbox — os números vêm preenchidos.
    assert isinstance(stats["cpu"], (int, float))
    assert isinstance(stats["ram"], (int, float))
    assert isinstance(stats["disco"], (int, float))
    assert stats["ram_total_gb"] > 0
    assert stats["disco_total_gb"] > 0
    assert len(stats["hora"]) == 5 and stats["hora"][2] == ":"


def test_get_stats_taxa_de_rede_so_aparece_a_partir_da_segunda_chamada():
    import interface.status_info as status_info_mod

    status_info_mod._last_net_sample = None  # garante que esta chamada é "a primeira"

    first = get_stats()
    assert first["net_sent_kbps"] is None
    assert first["net_recv_kbps"] is None

    second = get_stats()
    assert isinstance(second["net_sent_kbps"], (int, float))
    assert isinstance(second["net_recv_kbps"], (int, float))
    assert second["net_sent_kbps"] >= 0
    assert second["net_recv_kbps"] >= 0


def test_get_stats_nunca_levanta_excecao_mesmo_com_psutil_quebrado(monkeypatch):
    import interface.status_info as status_info_mod

    real_import = __import__

    def _broken_import(name, *args, **kwargs):
        if name == "psutil":
            raise RuntimeError("psutil indisponível neste ambiente")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _broken_import)

    stats = status_info_mod.get_stats()

    assert stats["cpu"] is None
    assert stats["ram"] is None
    assert stats["disco"] is None
    assert stats["net_sent_kbps"] is None
    assert stats["hora"] is not None  # a hora não depende do psutil


def _reset_process_cache():
    import interface.status_info as status_info_mod

    status_info_mod._process_cache_time = None
    status_info_mod._process_cache_result = []
    status_info_mod._process_cache.clear()


def test_get_top_processes_devolve_processos_reais_ordenados():
    _reset_process_cache()
    # psutil está instalado neste sandbox, então sempre existe pelo menos
    # o próprio processo do teste rodando — não fabricamos nomes.
    rows = get_top_processes(limit=5)

    assert 0 < len(rows) <= 5
    for row in rows:
        assert set(row.keys()) == {"name", "cpu", "mem", "status"}
        assert isinstance(row["name"], str) and row["name"]
    # ordenado do maior pro menor uso de CPU (e, em empate, de memória)
    cpu_values = [r["cpu"] for r in rows]
    assert cpu_values == sorted(cpu_values, reverse=True)


def test_get_top_processes_nunca_levanta_excecao_sem_psutil(monkeypatch):
    import interface.status_info as status_info_mod

    _reset_process_cache()
    real_import = __import__

    def _broken_import(name, *args, **kwargs):
        if name == "psutil":
            raise RuntimeError("psutil indisponível neste ambiente")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _broken_import)

    assert status_info_mod.get_top_processes() == []


def test_get_top_processes_usa_cache_e_so_revarre_todos_os_processos_apos_o_ttl(monkeypatch):
    """
    Esta é a otimização que resolveu o Jarvis "pesado": antes, cada
    poll de 1s da interface varria TODOS os processos do sistema (a
    causa real da lentidão relatada); agora só revarre a cada
    `_PROCESS_CACHE_TTL` segundos e devolve o resultado guardado nas
    chamadas entre um TTL e outro.
    """
    import psutil

    import interface.status_info as status_info_mod

    _reset_process_cache()

    calls = {"n": 0}
    real_pids = psutil.pids

    def counting_pids():
        calls["n"] += 1
        return real_pids()

    monkeypatch.setattr(psutil, "pids", counting_pids)

    fake_now = [1000.0]
    monkeypatch.setattr(status_info_mod.time, "monotonic", lambda: fake_now[0])

    first = get_top_processes(limit=3)
    assert calls["n"] == 1
    assert len(first) > 0

    # ainda dentro do TTL: devolve o cache, sem varrer os processos de novo.
    fake_now[0] += 1.0
    second = get_top_processes(limit=3)
    assert calls["n"] == 1
    assert second == first

    # depois do TTL: varre de novo.
    fake_now[0] += status_info_mod._PROCESS_CACHE_TTL + 1.0
    get_top_processes(limit=3)
    assert calls["n"] == 2


def _fake_agent(llm_available: bool) -> MagicMock:
    agent = MagicMock()
    agent.llm.available = llm_available
    return agent


def test_get_module_rows_tem_as_nove_linhas_esperadas(monkeypatch):
    monkeypatch.setattr(settings, "spotify_client_id", "")
    monkeypatch.setattr(settings, "spotify_client_secret", "")
    monkeypatch.setattr(settings, "discord_bot_token", "")
    monkeypatch.setattr(settings, "github_token", "")

    rows = get_module_rows(_fake_agent(llm_available=True))

    labels = [row["label"] for row in rows]
    assert labels == [
        "Inteligência (IA)",
        "Voz de entrada",
        "Voz de saída",
        "Voz contínua",
        "Memória",
        "Spotify",
        "Bot do Discord",
        "GitHub",
        "Google (Gmail/Calendar/Drive)",
    ]
    assert all("label" in r and "detail" in r and "ok" in r for r in rows)
    assert all(r["category"] in {"core", "integration"} for r in rows)
    core_labels = {r["label"] for r in rows if r["category"] == "core"}
    assert core_labels == {"Inteligência (IA)", "Voz de entrada", "Voz de saída", "Voz contínua", "Memória"}


def test_get_module_rows_reflete_ia_indisponivel(monkeypatch):
    monkeypatch.setattr(settings, "llm_auto_fallback", False)

    rows = get_module_rows(_fake_agent(llm_available=False))

    ia_row = next(r for r in rows if r["label"] == "Inteligência (IA)")
    assert ia_row["ok"] is False
    assert "indisponível" in ia_row["detail"]


def test_get_module_rows_reflete_spotify_configurado(monkeypatch):
    monkeypatch.setattr(settings, "spotify_client_id", "abc123")
    monkeypatch.setattr(settings, "spotify_client_secret", "segredo")

    rows = get_module_rows(_fake_agent(llm_available=True))

    spotify_row = next(r for r in rows if r["label"] == "Spotify")
    assert spotify_row["ok"] is True
    assert spotify_row["detail"] in {"Configurado", "Conectado"}


def test_get_activity_rows_vazio_sem_atividades():
    assert get_activity_rows() == []


def test_get_activity_rows_ordem_mais_antiga_primeiro():
    from memory.database import log_activity

    log_activity("primeira ação")
    log_activity("segunda ação")

    rows = get_activity_rows(limit=10)

    assert [r["description"] for r in rows] == ["primeira ação", "segunda ação"]
    assert all("time" in r for r in rows)


def test_get_activity_rows_respeita_limit():
    from memory.database import log_activity

    for i in range(5):
        log_activity(f"ação {i}")

    rows = get_activity_rows(limit=2)

    assert len(rows) == 2
    # as duas mais recentes, na ordem "mais antiga primeiro"
    assert [r["description"] for r in rows] == ["ação 3", "ação 4"]


def test_get_activity_rows_nunca_levanta_excecao_com_banco_quebrado(monkeypatch):
    import memory.database as database_mod

    def _broken_recent_activities(limit=20):
        raise RuntimeError("banco indisponível")

    monkeypatch.setattr(database_mod, "recent_activities", _broken_recent_activities)

    assert get_activity_rows() == []
