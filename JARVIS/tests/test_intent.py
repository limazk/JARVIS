"""Testes do parser de intenção local (core/intent.py) — seção 40 do spec."""
from core.intent import match_local_intent


def test_reconhece_hora():
    m = match_local_intent("que horas são")
    assert m.matched and m.tool_name == "get_time"


def test_reconhece_bom_dia_como_briefing_matinal():
    for frase in ("bom dia", "Bom dia!", "bom dia, jarvis", "bom dia jarvis"):
        m = match_local_intent(frase)
        assert m.matched and m.tool_name == "morning_briefing", frase


def test_reconhece_pedido_de_resumo_da_manha():
    m = match_local_intent("me dá um resumo da manhã")
    assert m.matched and m.tool_name == "morning_briefing"


def test_bom_dia_seguido_de_mais_coisa_nao_vira_briefing_automatico():
    # "bom dia" sozinho dispara o briefing; "bom dia, [pedido específico]"
    # deve continuar indo pro fluxo normal (LLM), não ser tratado como
    # o mesmo comando — evita sequestrar qualquer frase que comece com
    # a saudação.
    m = match_local_intent("bom dia, pode abrir o navegador pra mim?")
    assert m.matched is False or m.tool_name != "morning_briefing"


def test_reconhece_abrir_app():
    m = match_local_intent("abre o spotify")
    assert m.matched and m.tool_name == "open_application"
    assert m.params["app_name"] == "spotify"


def test_reconhece_calculo():
    m = match_local_intent("calcula 10 + 5")
    assert m.matched and m.tool_name == "calculate"
    assert m.params["expression"] == "10 + 5"


def test_reconhece_lembrete():
    m = match_local_intent("me lembra às 18h de estudar")
    assert m.matched and m.tool_name == "add_reminder"


def test_reconhece_lembrar_fato_de_longo_prazo():
    m = match_local_intent("lembra que meu editor é o VS Code")
    assert m.matched and m.tool_name == "remember_fact"


def test_reconhece_nota():
    m = match_local_intent("anota comprar carregador")
    assert m.matched and m.tool_name == "add_note"
    assert m.params["text"] == "comprar carregador"


def test_reconhece_status_sistema_ram():
    m = match_local_intent("quanto de RAM estou usando")
    assert m.matched and m.tool_name == "system_status"


def test_frase_sem_padrao_local_nao_bate():
    m = match_local_intent("me conte uma piada sobre gatos")
    assert not m.matched


def test_reconhece_tocar_musica_no_spotify():
    m = match_local_intent("toca bohemian rhapsody")
    assert m.matched and m.tool_name == "spotify_play"
    assert m.params["query"] == "bohemian rhapsody"


def test_reconhece_pausar_musica():
    m = match_local_intent("pausa a música")
    assert m.matched and m.tool_name == "spotify_pause"


def test_reconhece_proxima_musica():
    m = match_local_intent("próxima música")
    assert m.matched and m.tool_name == "spotify_next"


def test_reconhece_o_que_esta_tocando():
    m = match_local_intent("o que está tocando no spotify")
    assert m.matched and m.tool_name == "spotify_now_playing"


def test_reconhece_tocar_musica_de_uma_playlist_especifica():
    m = match_local_intent("toca undressed da minha playlist rock")
    assert m.matched and m.tool_name == "spotify_play"
    assert m.params == {"query": "undressed", "playlist": "rock"}


def test_reconhece_tocar_playlist_inteira():
    m = match_local_intent("toca minha playlist treino")
    assert m.matched and m.tool_name == "spotify_play_playlist"
    assert m.params["name"] == "treino"


def test_reconhece_listar_playlists():
    m = match_local_intent("mostra minhas playlists")
    assert m.matched and m.tool_name == "spotify_list_playlists"


def test_reconhece_adicionar_na_fila():
    m = match_local_intent("adiciona bohemian rhapsody na fila")
    assert m.matched and m.tool_name == "spotify_add_to_queue"
    assert m.params["query"] == "bohemian rhapsody"


def test_reconhece_ativar_shuffle():
    m = match_local_intent("ativa o shuffle")
    assert m.matched and m.tool_name == "spotify_toggle_shuffle"
    assert m.params["enabled"] is True


def test_reconhece_desativar_shuffle():
    m = match_local_intent("desativa o modo aleatorio do spotify")
    assert m.matched and m.tool_name == "spotify_toggle_shuffle"
    assert m.params["enabled"] is False


def test_reconhece_curtir_musica_atual():
    m = match_local_intent("curte essa musica")
    assert m.matched and m.tool_name == "spotify_save_current_track"


def test_reconhece_email_nao_lido():
    m = match_local_intent("tenho email novo")
    assert m.matched and m.tool_name == "list_unread_emails"


def test_reconhece_compromissos_de_hoje():
    m = match_local_intent("que compromissos eu tenho hoje")
    assert m.matched and m.tool_name == "list_upcoming_events"
