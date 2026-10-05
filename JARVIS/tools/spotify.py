"""
Controle de reprodução do Spotify — item do roadmap ("hoje só abre o
app") pedido explicitamente pelo usuário.

Diferente de `tools/apps.py::open_application("spotify")` (que só abre
o programa), este módulo fala com a Web API do Spotify pra tocar,
pausar, pular faixa e ajustar volume de dentro do próprio Jarvis.

Duas coisas importantes que NÃO dá pra contornar (são limitações da
API do Spotify, não do Jarvis):
1. Precisa de um "app" cadastrado grátis em
   https://developer.spotify.com/dashboard (Client ID + Client Secret)
   com a Redirect URI `http://127.0.0.1:8888/callback` cadastrada lá
   (tem que ser IDÊNTICA à configurada em SPOTIFY_REDIRECT_URI).
2. Os endpoints de CONTROLE (tocar/pausar/pular/volume) só funcionam
   com conta Spotify Premium — conta grátis consegue só consultar o
   que está tocando (`spotify_now_playing`). Isso é restrição da
   própria Spotify, retornada como erro 403 pela API.

Autenticação: na primeira vez que qualquer comando aqui for usado, o
Jarvis abre o navegador pedindo login/autorização na sua conta
Spotify (fluxo OAuth padrão via `spotipy`); depois disso o token fica
em cache (`.spotify_cache`, ao lado do `.env`) e os pedidos seguintes
não abrem o navegador de novo.

Se você já usava uma versão anterior do Jarvis (com menos permissões
do Spotify) e agora as novas funções de playlist/fila/curtir não
funcionarem de primeira, é só apagar o arquivo `.spotify_cache` — o
Jarvis pede login de novo automaticamente e o Spotify vai perguntar
se você autoriza os novos escopos (`playlist-read-private`,
`user-library-modify`).
"""
from __future__ import annotations

from typing import Optional

from config.settings import settings
from core.permissions import RiskLevel
from tools.base import Tool, ToolResult

_SCOPES = (
    "user-read-playback-state user-modify-playback-state user-read-currently-playing "
    "playlist-read-private user-library-modify"
)

_client_cache = None  # guarda o cliente autenticado entre chamadas (evita reautenticar toda hora)


def _get_client():
    """
    Devolve um cliente spotipy autenticado, ou None se faltar
    configuração. Import feito aqui dentro (não no topo do arquivo) —
    mesmo padrão de tools/system.py com pycaw: se `spotipy` não
    estiver instalado, o resto do Jarvis continua funcionando normal.
    """
    global _client_cache
    if _client_cache is not None:
        return _client_cache

    if not settings.spotify_client_id or not settings.spotify_client_secret:
        return None

    try:
        import spotipy
        from spotipy.oauth2 import SpotifyOAuth
    except ImportError:
        return None

    auth_manager = SpotifyOAuth(
        client_id=settings.spotify_client_id,
        client_secret=settings.spotify_client_secret,
        redirect_uri=settings.spotify_redirect_uri,
        scope=_SCOPES,
        cache_path=str(settings.base_dir / ".spotify_cache"),
        open_browser=True,
    )
    _client_cache = spotipy.Spotify(auth_manager=auth_manager)
    return _client_cache


def _no_credentials_result() -> ToolResult:
    return ToolResult(
        success=False,
        message=(
            "Preciso de SPOTIFY_CLIENT_ID e SPOTIFY_CLIENT_SECRET no .env pra controlar o Spotify "
            "(veja o topo de tools/spotify.py ou o README pra criar o app grátis em "
            "developer.spotify.com/dashboard)."
        ),
    )


def _active_device_id(sp) -> Optional[str]:
    """Prefere o dispositivo já ativo; se nenhum estiver ativo, usa o primeiro disponível."""
    try:
        devices = sp.devices().get("devices", [])
    except Exception:
        return None
    if not devices:
        return None
    active = next((d for d in devices if d.get("is_active")), None)
    return (active or devices[0])["id"]


def _friendly_error(exc: Exception) -> str:
    status = getattr(exc, "http_status", None)
    reason = getattr(exc, "reason", None) or ""
    if reason == "NO_ACTIVE_DEVICE" or status == 404:
        return "Não achei nenhum Spotify aberto. Abra o app (ou o Spotify Web) em algum dispositivo e tente de novo."
    if status == 403:
        return "O Spotify recusou o comando — controle de reprodução pela API exige conta Spotify Premium."
    return f"O Spotify recusou o comando: {exc}"


def _best_match(query: str, items: list[dict]) -> dict:
    """
    Escolhe, entre os resultados da busca, o que tem o NOME mais parecido
    com o que foi pedido — em vez de simplesmente confiar que o primeiro
    resultado da Spotify é o certo.

    Por quê: a busca da Spotify usa relevância personalizada (histórico de
    audição, popularidade, etc.), então pra uma busca simples (ex.:
    "undressed") ela pode devolver em 1º lugar uma música bem diferente
    que o usuário costuma ouvir mais, em vez da música cujo nome bate com
    o texto pesquisado. Comparando o texto da busca com o nome de cada
    candidato, evitamos esse tipo de "acerto errado".
    """
    import difflib

    query_norm = query.strip().lower()
    return max(items, key=lambda item: difflib.SequenceMatcher(None, query_norm, item.get("name", "").lower()).ratio())


def _all_user_playlists(sp) -> list[dict]:
    """Busca as playlists do usuário (as suas + as que ele segue), com paginação básica."""
    playlists: list[dict] = []
    limit = 50
    offset = 0
    while True:
        page = sp.current_user_playlists(limit=limit, offset=offset)
        items = page.get("items", [])
        playlists.extend(items)
        if not page.get("next") or len(playlists) >= 200:
            break
        offset += limit
    return playlists


def _find_playlist(sp, name: str, threshold: float = 0.35) -> Optional[dict]:
    """
    Acha a playlist do usuário cujo nome mais parece com `name`.

    Diferente de `_best_match` (usado nas buscas de música, onde a Spotify
    já devolveu candidatos relevantes), aqui comparamos contra TODAS as
    playlists do usuário — então usamos um limiar mínimo de parecença
    (`threshold`) pra não "inventar" uma playlist qualquer quando nenhuma
    bate de verdade com o nome pedido.
    """
    import difflib

    playlists = _all_user_playlists(sp)
    if not playlists:
        return None
    name_norm = name.strip().lower()
    scored = [
        (difflib.SequenceMatcher(None, name_norm, (p.get("name") or "").lower()).ratio(), p)
        for p in playlists
    ]
    best_score, best_playlist = max(scored, key=lambda pair: pair[0])
    return best_playlist if best_score >= threshold else None


def _playlist_not_found_message(sp, name: str) -> str:
    """Mensagem honesta de erro — já sugere os nomes reais das playlists do usuário, se houver."""
    try:
        playlists = _all_user_playlists(sp)
    except Exception:
        playlists = []
    if not playlists:
        return f"Não achei nenhuma playlist parecida com '{name}' (ou você não tem nenhuma playlist salva)."
    nomes = ", ".join(f"'{p.get('name')}'" for p in playlists[:8] if p.get("name"))
    return f"Não achei nenhuma playlist parecida com '{name}'. Suas playlists incluem: {nomes}."


def spotify_play(query: str = "", playlist: str = "", **_: object) -> ToolResult:
    sp = _get_client()
    if sp is None:
        return _no_credentials_result()

    try:
        import spotipy

        device_id = _active_device_id(sp)

        # Caso "toca X da minha playlist Y": restringe a busca aos itens
        # DESSA playlist, em vez do catálogo geral do Spotify.
        if playlist.strip():
            pl = _find_playlist(sp, playlist)
            if pl is None:
                return ToolResult(success=False, message=_playlist_not_found_message(sp, playlist))

            if not query.strip():
                # Só o nome da playlist foi dado — toca ela inteira.
                sp.start_playback(device_id=device_id, context_uri=pl["uri"])
                return ToolResult(success=True, message=f"Tocando a playlist '{pl['name']}' no Spotify.")

            tracks: list[dict] = []
            fields = "items(track(uri,name,artists(name))),next"
            results = sp.playlist_items(pl["id"], fields=fields, additional_types=["track"])
            while results:
                for item in results.get("items", []):
                    track = item.get("track")
                    if track and track.get("uri"):
                        tracks.append(track)
                results = sp.next(results) if results.get("next") else None

            if not tracks:
                return ToolResult(success=False, message=f"A playlist '{pl['name']}' não tem músicas (ou está vazia pra mim).")

            track = _best_match(query, tracks)
            uri = track["uri"]
            nome = track["name"]
            artista = track["artists"][0]["name"] if track.get("artists") else ""
            sp.start_playback(device_id=device_id, context_uri=pl["uri"], offset={"uri": uri})
            return ToolResult(success=True, message=f"Tocando '{nome}' de {artista} (da playlist '{pl['name']}') no Spotify.")

        if query.strip():
            results = sp.search(q=query, type="track", limit=10)
            items = results.get("tracks", {}).get("items", [])
            if not items:
                return ToolResult(success=False, message=f"Não achei nada no Spotify parecido com '{query}'.")
            track = _best_match(query, items)
            uri = track["uri"]
            nome = track["name"]
            artista = track["artists"][0]["name"] if track.get("artists") else ""
            sp.start_playback(device_id=device_id, uris=[uri])
            return ToolResult(success=True, message=f"Tocando '{nome}' de {artista} no Spotify.")

        sp.start_playback(device_id=device_id)
        return ToolResult(success=True, message="Retomando a reprodução no Spotify.")
    except spotipy.exceptions.SpotifyException as exc:  # type: ignore[union-attr]
        return ToolResult(success=False, message=_friendly_error(exc))
    except Exception as exc:
        return ToolResult(success=False, message=f"Não consegui falar com o Spotify: {exc}")


def spotify_play_playlist(name: str, **_: object) -> ToolResult:
    """Toca uma playlist inteira do usuário pelo nome (ex.: 'toca minha playlist Treino')."""
    sp = _get_client()
    if sp is None:
        return _no_credentials_result()
    try:
        import spotipy

        pl = _find_playlist(sp, name)
        if pl is None:
            return ToolResult(success=False, message=_playlist_not_found_message(sp, name))
        sp.start_playback(device_id=_active_device_id(sp), context_uri=pl["uri"])
        return ToolResult(success=True, message=f"Tocando a playlist '{pl['name']}' no Spotify.")
    except spotipy.exceptions.SpotifyException as exc:  # type: ignore[union-attr]
        return ToolResult(success=False, message=_friendly_error(exc))
    except Exception as exc:
        return ToolResult(success=False, message=f"Não consegui falar com o Spotify: {exc}")


def spotify_list_playlists(**_: object) -> ToolResult:
    """Lista as playlists do usuário (as suas + as que ele segue)."""
    sp = _get_client()
    if sp is None:
        return _no_credentials_result()
    try:
        playlists = _all_user_playlists(sp)
    except Exception as exc:
        return ToolResult(success=False, message=f"Não consegui falar com o Spotify: {exc}")

    if not playlists:
        return ToolResult(success=True, message="Você não tem nenhuma playlist salva no Spotify.")
    nomes = "\n".join(f"- {p.get('name')} ({p.get('tracks', {}).get('total', '?')} músicas)" for p in playlists)
    return ToolResult(success=True, message=f"Suas playlists:\n{nomes}")


def spotify_add_to_queue(query: str, **_: object) -> ToolResult:
    """Adiciona uma música à fila do Spotify, sem interromper o que está tocando agora."""
    sp = _get_client()
    if sp is None:
        return _no_credentials_result()
    try:
        import spotipy

        results = sp.search(q=query, type="track", limit=10)
        items = results.get("tracks", {}).get("items", [])
        if not items:
            return ToolResult(success=False, message=f"Não achei nada no Spotify parecido com '{query}'.")
        track = _best_match(query, items)
        sp.add_to_queue(track["uri"], device_id=_active_device_id(sp))
        artista = track["artists"][0]["name"] if track.get("artists") else ""
        return ToolResult(success=True, message=f"Adicionei '{track['name']}' de {artista} à fila do Spotify.")
    except spotipy.exceptions.SpotifyException as exc:  # type: ignore[union-attr]
        return ToolResult(success=False, message=_friendly_error(exc))
    except Exception as exc:
        return ToolResult(success=False, message=f"Não consegui falar com o Spotify: {exc}")


def spotify_toggle_shuffle(enabled: bool, **_: object) -> ToolResult:
    sp = _get_client()
    if sp is None:
        return _no_credentials_result()
    try:
        import spotipy

        sp.shuffle(bool(enabled), device_id=_active_device_id(sp))
        return ToolResult(success=True, message=f"Modo aleatório {'ativado' if enabled else 'desativado'} no Spotify.")
    except spotipy.exceptions.SpotifyException as exc:  # type: ignore[union-attr]
        return ToolResult(success=False, message=_friendly_error(exc))
    except Exception as exc:
        return ToolResult(success=False, message=f"Não consegui falar com o Spotify: {exc}")


def spotify_save_current_track(**_: object) -> ToolResult:
    """Curte (salva em 'Músicas Curtidas') a música que está tocando agora."""
    sp = _get_client()
    if sp is None:
        return _no_credentials_result()
    try:
        import spotipy

        current = sp.current_playback()
        if not current or not current.get("item"):
            return ToolResult(success=False, message="Nada tocando no Spotify agora pra curtir.")
        item = current["item"]
        sp.current_user_saved_tracks_add([item["id"]])
        artista = item.get("artists", [{}])[0].get("name", "?")
        return ToolResult(success=True, message=f"Curti '{item.get('name', '?')}' de {artista} — salva em Músicas Curtidas.")
    except spotipy.exceptions.SpotifyException as exc:  # type: ignore[union-attr]
        return ToolResult(success=False, message=_friendly_error(exc))
    except Exception as exc:
        return ToolResult(success=False, message=f"Não consegui falar com o Spotify: {exc}")


def spotify_pause(**_: object) -> ToolResult:
    sp = _get_client()
    if sp is None:
        return _no_credentials_result()
    try:
        import spotipy

        sp.pause_playback(device_id=_active_device_id(sp))
        return ToolResult(success=True, message="Música pausada.")
    except spotipy.exceptions.SpotifyException as exc:  # type: ignore[union-attr]
        return ToolResult(success=False, message=_friendly_error(exc))
    except Exception as exc:
        return ToolResult(success=False, message=f"Não consegui falar com o Spotify: {exc}")


def spotify_next(**_: object) -> ToolResult:
    sp = _get_client()
    if sp is None:
        return _no_credentials_result()
    try:
        import spotipy

        sp.next_track(device_id=_active_device_id(sp))
        return ToolResult(success=True, message="Pulei para a próxima faixa.")
    except spotipy.exceptions.SpotifyException as exc:  # type: ignore[union-attr]
        return ToolResult(success=False, message=_friendly_error(exc))
    except Exception as exc:
        return ToolResult(success=False, message=f"Não consegui falar com o Spotify: {exc}")


def spotify_previous(**_: object) -> ToolResult:
    sp = _get_client()
    if sp is None:
        return _no_credentials_result()
    try:
        import spotipy

        sp.previous_track(device_id=_active_device_id(sp))
        return ToolResult(success=True, message="Voltei para a faixa anterior.")
    except spotipy.exceptions.SpotifyException as exc:  # type: ignore[union-attr]
        return ToolResult(success=False, message=_friendly_error(exc))
    except Exception as exc:
        return ToolResult(success=False, message=f"Não consegui falar com o Spotify: {exc}")


def spotify_set_volume(level: int, **_: object) -> ToolResult:
    level = max(0, min(100, int(level)))
    sp = _get_client()
    if sp is None:
        return _no_credentials_result()
    try:
        import spotipy

        sp.volume(level, device_id=_active_device_id(sp))
        return ToolResult(success=True, message=f"Volume do Spotify ajustado para {level}%.")
    except spotipy.exceptions.SpotifyException as exc:  # type: ignore[union-attr]
        return ToolResult(success=False, message=_friendly_error(exc))
    except Exception as exc:
        return ToolResult(success=False, message=f"Não consegui falar com o Spotify: {exc}")


def spotify_now_playing(**_: object) -> ToolResult:
    sp = _get_client()
    if sp is None:
        return _no_credentials_result()
    try:
        import spotipy

        current = sp.current_playback()
    except spotipy.exceptions.SpotifyException as exc:  # type: ignore[union-attr]
        return ToolResult(success=False, message=_friendly_error(exc))
    except Exception as exc:
        return ToolResult(success=False, message=f"Não consegui falar com o Spotify: {exc}")

    if not current or not current.get("item"):
        return ToolResult(success=True, message="Nada tocando no Spotify agora.")

    item = current["item"]
    nome = item.get("name", "?")
    artista = item.get("artists", [{}])[0].get("name", "?")
    estado = "tocando" if current.get("is_playing") else "pausado"
    return ToolResult(success=True, message=f"{estado.capitalize()}: '{nome}' de {artista}.", data=current)


def register(registry) -> None:
    registry.register(Tool(
        name="spotify_play",
        description=(
            "Toca uma música/artista específico no Spotify (parâmetro 'query'), ou retoma a reprodução "
            "pausada se 'query' vier vazio. Se o usuário mencionar uma playlist específica dele "
            "('da minha playlist X', 'na playlist Y'), passe o nome dela em 'playlist' — aí a busca "
            "acontece só dentro dessa playlist, em vez do catálogo geral do Spotify. Requer Spotify "
            "Premium e o app já aberto em algum dispositivo."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Nome da música/artista, opcional"},
                "playlist": {"type": "string", "description": "Nome de uma playlist do usuário, opcional"},
            },
        },
        risk_level=RiskLevel.LOW,
        handler=spotify_play,
    ))
    registry.register(Tool(
        name="spotify_play_playlist",
        description="Toca uma playlist inteira do usuário pelo nome (ex.: 'toca minha playlist Treino').",
        parameters={
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Nome da playlist"}},
            "required": ["name"],
        },
        risk_level=RiskLevel.LOW,
        handler=spotify_play_playlist,
    ))
    registry.register(Tool(
        name="spotify_list_playlists",
        description="Lista as playlists do usuário no Spotify (as dele e as que ele segue).",
        parameters={"type": "object", "properties": {}},
        risk_level=RiskLevel.LOW,
        handler=spotify_list_playlists,
    ))
    registry.register(Tool(
        name="spotify_add_to_queue",
        description="Adiciona uma música à fila do Spotify sem interromper o que está tocando agora.",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Nome da música/artista"}},
            "required": ["query"],
        },
        risk_level=RiskLevel.LOW,
        handler=spotify_add_to_queue,
    ))
    registry.register(Tool(
        name="spotify_toggle_shuffle",
        description="Ativa ou desativa o modo aleatório (shuffle) da reprodução atual no Spotify.",
        parameters={
            "type": "object",
            "properties": {"enabled": {"type": "boolean", "description": "true pra ativar, false pra desativar"}},
            "required": ["enabled"],
        },
        risk_level=RiskLevel.LOW,
        handler=spotify_toggle_shuffle,
    ))
    registry.register(Tool(
        name="spotify_save_current_track",
        description="Curte (salva em 'Músicas Curtidas') a música que está tocando agora no Spotify.",
        parameters={"type": "object", "properties": {}},
        risk_level=RiskLevel.LOW,
        handler=spotify_save_current_track,
    ))
    registry.register(Tool(
        name="spotify_pause",
        description="Pausa a reprodução atual no Spotify.",
        parameters={"type": "object", "properties": {}},
        risk_level=RiskLevel.LOW,
        handler=spotify_pause,
    ))
    registry.register(Tool(
        name="spotify_next",
        description="Pula para a próxima faixa no Spotify.",
        parameters={"type": "object", "properties": {}},
        risk_level=RiskLevel.LOW,
        handler=spotify_next,
    ))
    registry.register(Tool(
        name="spotify_previous",
        description="Volta para a faixa anterior no Spotify.",
        parameters={"type": "object", "properties": {}},
        risk_level=RiskLevel.LOW,
        handler=spotify_previous,
    ))
    registry.register(Tool(
        name="spotify_set_volume",
        description="Ajusta o volume da reprodução do Spotify (0 a 100) — diferente do volume geral do Windows.",
        parameters={
            "type": "object",
            "properties": {"level": {"type": "integer", "description": "Nível de 0 a 100"}},
            "required": ["level"],
        },
        risk_level=RiskLevel.LOW,
        handler=spotify_set_volume,
        confirmation_template="Ajustar volume do Spotify para {level}%",
    ))
    registry.register(Tool(
        name="spotify_now_playing",
        description="Diz o que está tocando no Spotify agora (funciona mesmo sem conta Premium).",
        parameters={"type": "object", "properties": {}},
        risk_level=RiskLevel.LOW,
        handler=spotify_now_playing,
    ))
