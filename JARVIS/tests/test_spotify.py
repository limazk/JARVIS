"""
Testes do controle de reprodução do Spotify (tools/spotify.py).

`spotipy` não está disponível neste sandbox de testes (sem acesso ao
índice do PyPI) — instalamos um módulo fake mínimo em `sys.modules`
com só o que `tools/spotify.py` referencia (`spotipy.exceptions.
SpotifyException`), pra poder testar os caminhos de sucesso/erro sem
precisar da biblioteca de verdade. Isso não muda nada pro uso real:
no Windows do usuário, `pip install -r requirements.txt` instala o
spotipy de verdade, que nunca chega a ser substituído por isto.
"""
from __future__ import annotations

import sys
import types

import pytest

from config.settings import settings


def _install_fake_spotipy():
    fake = types.ModuleType("spotipy")
    fake._jarvis_fake = True  # type: ignore[attr-defined]
    exceptions_mod = types.ModuleType("spotipy.exceptions")

    class SpotifyException(Exception):
        def __init__(self, http_status=None, reason=None, msg="erro"):
            super().__init__(msg)
            self.http_status = http_status
            self.reason = reason

    exceptions_mod.SpotifyException = SpotifyException
    fake.exceptions = exceptions_mod
    sys.modules["spotipy"] = fake
    sys.modules["spotipy.exceptions"] = exceptions_mod
    return fake


@pytest.fixture(autouse=True)
def _fake_spotipy_module():
    _install_fake_spotipy()
    yield
    sys.modules.pop("spotipy", None)
    sys.modules.pop("spotipy.exceptions", None)


class _FakeSpotifyClient:
    def __init__(self) -> None:
        self.calls: list = []
        self._devices = [{"id": "dev1", "is_active": True}]
        self._current = None
        self._playlists: list = []
        self._playlist_tracks: dict = {}

    def devices(self):
        return {"devices": self._devices}

    def search(self, q, type, limit):
        self.calls.append(("search", q))
        return {
            "tracks": {
                "items": [{"uri": "spotify:track:abc", "name": "Test Song", "artists": [{"name": "Test Artist"}]}]
            }
        }

    def start_playback(self, device_id=None, uris=None, context_uri=None, offset=None):
        self.calls.append(("start_playback", device_id, uris, context_uri, offset))

    def pause_playback(self, device_id=None):
        self.calls.append(("pause_playback", device_id))

    def next_track(self, device_id=None):
        self.calls.append(("next_track", device_id))

    def previous_track(self, device_id=None):
        self.calls.append(("previous_track", device_id))

    def volume(self, level, device_id=None):
        self.calls.append(("volume", level, device_id))

    def current_playback(self):
        return self._current

    def current_user_playlists(self, limit=50, offset=0):
        return {"items": self._playlists[offset : offset + limit], "next": None}

    def playlist_items(self, playlist_id, fields=None, additional_types=None):
        tracks = self._playlist_tracks.get(playlist_id, [])
        return {"items": [{"track": t} for t in tracks], "next": None}

    def add_to_queue(self, uri, device_id=None):
        self.calls.append(("add_to_queue", uri, device_id))

    def shuffle(self, state, device_id=None):
        self.calls.append(("shuffle", state, device_id))

    def current_user_saved_tracks_add(self, ids):
        self.calls.append(("save_tracks", ids))


def test_sem_credenciais_retorna_erro_amigavel(monkeypatch):
    from tools import spotify

    monkeypatch.setattr(settings, "spotify_client_id", "")
    monkeypatch.setattr(spotify, "_client_cache", None)

    result = spotify.spotify_play(query="alguma coisa")

    assert not result.success
    assert "SPOTIFY_CLIENT_ID" in result.message


def test_spotify_play_com_busca_toca_a_musica_certa(monkeypatch):
    from tools import spotify

    fake = _FakeSpotifyClient()
    monkeypatch.setattr(spotify, "_get_client", lambda: fake)

    result = spotify.spotify_play(query="bohemian rhapsody")

    assert result.success
    assert "Test Song" in result.message
    assert "Test Artist" in result.message
    assert ("start_playback", "dev1", ["spotify:track:abc"], None, None) in fake.calls


def test_spotify_play_sem_query_retoma_reproducao(monkeypatch):
    from tools import spotify

    fake = _FakeSpotifyClient()
    monkeypatch.setattr(spotify, "_get_client", lambda: fake)

    result = spotify.spotify_play()

    assert result.success
    assert ("start_playback", "dev1", None, None, None) in fake.calls


def test_spotify_pause(monkeypatch):
    from tools import spotify

    fake = _FakeSpotifyClient()
    monkeypatch.setattr(spotify, "_get_client", lambda: fake)

    result = spotify.spotify_pause()

    assert result.success
    assert ("pause_playback", "dev1") in fake.calls


def test_spotify_now_playing_formata_musica_atual(monkeypatch):
    from tools import spotify

    fake = _FakeSpotifyClient()
    fake._current = {"is_playing": True, "item": {"name": "Test Song", "artists": [{"name": "Test Artist"}]}}
    monkeypatch.setattr(spotify, "_get_client", lambda: fake)

    result = spotify.spotify_now_playing()

    assert result.success
    assert "Test Song" in result.message
    assert "Test Artist" in result.message


def test_spotify_now_playing_nada_tocando(monkeypatch):
    from tools import spotify

    fake = _FakeSpotifyClient()
    monkeypatch.setattr(spotify, "_get_client", lambda: fake)

    result = spotify.spotify_now_playing()

    assert result.success
    assert "Nada tocando" in result.message


def test_spotify_sem_dispositivo_ativo_da_mensagem_amigavel(monkeypatch):
    from tools import spotify

    fake = _FakeSpotifyClient()
    fake._devices = []

    def _raise_no_device(device_id=None, uris=None, context_uri=None, offset=None):
        raise sys.modules["spotipy"].exceptions.SpotifyException(http_status=404, reason="NO_ACTIVE_DEVICE")

    fake.start_playback = _raise_no_device
    monkeypatch.setattr(spotify, "_get_client", lambda: fake)

    result = spotify.spotify_play()

    assert not result.success
    assert "Spotify" in result.message


def _fake_with_playlists() -> "_FakeSpotifyClient":
    fake = _FakeSpotifyClient()
    fake._playlists = [
        {"id": "pl1", "uri": "spotify:playlist:pl1", "name": "Rock Classico", "tracks": {"total": 2}},
        {"id": "pl2", "uri": "spotify:playlist:pl2", "name": "Treino Pesado", "tracks": {"total": 1}},
    ]
    fake._playlist_tracks = {
        "pl1": [
            {"uri": "spotify:track:1", "name": "Undressed", "artists": [{"name": "Sombr"}]},
            {"uri": "spotify:track:2", "name": "Friends", "artists": [{"name": "Chase Atlantic"}]},
        ]
    }
    return fake


def test_spotify_play_com_query_e_playlist_busca_so_dentro_da_playlist(monkeypatch):
    from tools import spotify

    fake = _fake_with_playlists()
    monkeypatch.setattr(spotify, "_get_client", lambda: fake)

    result = spotify.spotify_play(query="undressed", playlist="rock classico")

    assert result.success
    assert "Undressed" in result.message
    assert "Sombr" in result.message
    assert "Rock Classico" in result.message
    assert ("start_playback", "dev1", None, "spotify:playlist:pl1", {"uri": "spotify:track:1"}) in fake.calls


def test_spotify_play_so_com_nome_da_playlist_toca_ela_inteira(monkeypatch):
    from tools import spotify

    fake = _fake_with_playlists()
    monkeypatch.setattr(spotify, "_get_client", lambda: fake)

    result = spotify.spotify_play(playlist="treino pesado")

    assert result.success
    assert "Treino Pesado" in result.message


def test_spotify_play_playlist_pelo_nome(monkeypatch):
    from tools import spotify

    fake = _fake_with_playlists()
    monkeypatch.setattr(spotify, "_get_client", lambda: fake)

    result = spotify.spotify_play_playlist(name="treino")

    assert result.success
    assert "Treino Pesado" in result.message


def test_spotify_play_playlist_inexistente_sugere_as_playlists_reais(monkeypatch):
    from tools import spotify

    fake = _fake_with_playlists()
    monkeypatch.setattr(spotify, "_get_client", lambda: fake)

    result = spotify.spotify_play_playlist(name="algo-completamente-diferente-disso-tudo")

    assert not result.success
    assert "Rock Classico" in result.message
    assert "Treino Pesado" in result.message


def test_spotify_list_playlists(monkeypatch):
    from tools import spotify

    fake = _fake_with_playlists()
    monkeypatch.setattr(spotify, "_get_client", lambda: fake)

    result = spotify.spotify_list_playlists()

    assert result.success
    assert "Rock Classico" in result.message
    assert "Treino Pesado" in result.message


def test_spotify_list_playlists_vazia(monkeypatch):
    from tools import spotify

    fake = _FakeSpotifyClient()
    monkeypatch.setattr(spotify, "_get_client", lambda: fake)

    result = spotify.spotify_list_playlists()

    assert result.success
    assert "não tem nenhuma playlist" in result.message.lower()


def test_spotify_add_to_queue(monkeypatch):
    from tools import spotify

    fake = _FakeSpotifyClient()
    monkeypatch.setattr(spotify, "_get_client", lambda: fake)

    result = spotify.spotify_add_to_queue(query="bohemian rhapsody")

    assert result.success
    assert "fila" in result.message.lower()
    assert ("add_to_queue", "spotify:track:abc", "dev1") in fake.calls


def test_spotify_toggle_shuffle_liga_e_desliga(monkeypatch):
    from tools import spotify

    fake = _FakeSpotifyClient()
    monkeypatch.setattr(spotify, "_get_client", lambda: fake)

    ligado = spotify.spotify_toggle_shuffle(enabled=True)
    desligado = spotify.spotify_toggle_shuffle(enabled=False)

    assert ligado.success and "ativado" in ligado.message.lower()
    assert desligado.success and "desativado" in desligado.message.lower()
    assert ("shuffle", True, "dev1") in fake.calls
    assert ("shuffle", False, "dev1") in fake.calls


def test_spotify_save_current_track(monkeypatch):
    from tools import spotify

    fake = _FakeSpotifyClient()
    fake._current = {"is_playing": True, "item": {"id": "trk1", "name": "Test Song", "artists": [{"name": "Test Artist"}]}}
    monkeypatch.setattr(spotify, "_get_client", lambda: fake)

    result = spotify.spotify_save_current_track()

    assert result.success
    assert "Test Song" in result.message
    assert ("save_tracks", ["trk1"]) in fake.calls


def test_spotify_save_current_track_sem_nada_tocando(monkeypatch):
    from tools import spotify

    fake = _FakeSpotifyClient()
    monkeypatch.setattr(spotify, "_get_client", lambda: fake)

    result = spotify.spotify_save_current_track()

    assert not result.success
    assert "nada tocando" in result.message.lower()
