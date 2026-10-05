"""
Testes da integração com o Google (Gmail/Calendar/Drive) — item do
roadmap. `google-api-python-client`/`google-auth-oauthlib` não estão
disponíveis neste sandbox de testes (sem acesso ao índice do PyPI).
Como `tools/gmail.py`, `tools/gcalendar.py` e `tools/gdrive.py` só
importam essas bibliotecas indiretamente (via `tools/google_auth.py`,
chamado através de `get_google_service`), os testes de "caminho feliz"
aqui simplesmente monkeypatcham `get_google_service` para devolver um
serviço fake com a mesma forma de encadeamento de métodos da API real
do Google (`service.recurso().metodo(**kwargs).execute()`), sem
precisar da biblioteca de verdade nem de rede.
"""
from __future__ import annotations

from tools import gcalendar, gdrive, gmail
from tools.google_auth import no_google_credentials_result


class _FakeExecute:
    def __init__(self, result) -> None:
        self._result = result

    def execute(self):
        return self._result


class _FakeGmailService:
    def __init__(self, list_result: dict, get_results: dict) -> None:
        self._list_result = list_result
        self._get_results = get_results
        self.sent: list[dict] = []

    def users(self):
        return self

    def messages(self):
        return self

    def list(self, **kwargs):
        return _FakeExecute(self._list_result)

    def get(self, id, **kwargs):
        return _FakeExecute(self._get_results[id])

    def send(self, userId, body):
        self.sent.append(body)
        return _FakeExecute({"id": "sent-123"})


def test_sem_credenciais_configuradas_retorna_erro_amigavel(monkeypatch):
    monkeypatch.setattr(gmail, "get_google_service", lambda *a, **k: None)
    result = gmail.list_unread_emails()
    assert not result.success
    assert "google_credentials.json" in result.message


def test_list_unread_emails_sem_nenhum(monkeypatch):
    fake = _FakeGmailService(list_result={"messages": []}, get_results={})
    monkeypatch.setattr(gmail, "get_google_service", lambda *a, **k: fake)

    result = gmail.list_unread_emails()

    assert result.success
    assert "nenhum" in result.message.lower()


def test_list_unread_emails_formata_remetente_e_assunto(monkeypatch):
    fake = _FakeGmailService(
        list_result={"messages": [{"id": "m1"}]},
        get_results={
            "m1": {"payload": {"headers": [{"name": "From", "value": "chefe@empresa.com"}, {"name": "Subject", "value": "Reunião"}]}}
        },
    )
    monkeypatch.setattr(gmail, "get_google_service", lambda *a, **k: fake)

    result = gmail.list_unread_emails()

    assert result.success
    assert "chefe@empresa.com" in result.message
    assert "Reunião" in result.message


def test_send_email_monta_a_mensagem_e_envia(monkeypatch):
    fake = _FakeGmailService(list_result={}, get_results={})
    monkeypatch.setattr(gmail, "get_google_service", lambda *a, **k: fake)

    result = gmail.send_email(to="alguem@example.com", subject="Oi", body="Mensagem de teste")

    assert result.success
    assert "alguem@example.com" in result.message
    assert len(fake.sent) == 1
    assert "raw" in fake.sent[0]


class _FakeCalendarService:
    def __init__(self, events: list[dict], insert_calls: list) -> None:
        self._events = events
        self._insert_calls = insert_calls

    def events(self):
        return self

    def list(self, **kwargs):
        return _FakeExecute({"items": self._events})

    def insert(self, calendarId, body):
        self._insert_calls.append(body)
        return _FakeExecute({"id": "evt-1"})


def test_list_upcoming_events_sem_nenhum(monkeypatch):
    fake = _FakeCalendarService(events=[], insert_calls=[])
    monkeypatch.setattr(gcalendar, "get_google_service", lambda *a, **k: fake)

    result = gcalendar.list_upcoming_events()

    assert result.success
    assert "nenhum" in result.message.lower()


def test_list_upcoming_events_formata_compromissos(monkeypatch):
    fake = _FakeCalendarService(
        events=[{"summary": "Dentista", "start": {"dateTime": "2026-09-15T15:00:00-03:00"}}],
        insert_calls=[],
    )
    monkeypatch.setattr(gcalendar, "get_google_service", lambda *a, **k: fake)

    result = gcalendar.list_upcoming_events(days=7)

    assert result.success
    assert "Dentista" in result.message


def test_create_event_data_invalida_e_honesto(monkeypatch):
    fake = _FakeCalendarService(events=[], insert_calls=[])
    monkeypatch.setattr(gcalendar, "get_google_service", lambda *a, **k: fake)

    result = gcalendar.create_event(title="Reunião", start_iso="não é uma data")

    assert not result.success
    assert "não entendi" in result.message.lower()


def test_create_event_cria_com_sucesso(monkeypatch):
    insert_calls: list = []
    fake = _FakeCalendarService(events=[], insert_calls=insert_calls)
    monkeypatch.setattr(gcalendar, "get_google_service", lambda *a, **k: fake)

    result = gcalendar.create_event(title="Reunião", start_iso="2026-09-15T15:00:00", duration_minutes=30)

    assert result.success
    assert "Reunião" in result.message
    assert len(insert_calls) == 1
    assert insert_calls[0]["summary"] == "Reunião"


class _FakeDriveService:
    def __init__(self, files: list[dict]) -> None:
        self._files = files
        self.last_query: str = ""

    def files(self):
        return self

    def list(self, q, **kwargs):
        self.last_query = q
        return _FakeExecute({"files": self._files})


def test_search_drive_files_sem_resultado(monkeypatch):
    fake = _FakeDriveService(files=[])
    monkeypatch.setattr(gdrive, "get_google_service", lambda *a, **k: fake)

    result = gdrive.search_drive_files(query="relatorio-x")

    assert result.success
    assert "não achei" in result.message.lower()


def test_search_drive_files_com_resultado(monkeypatch):
    fake = _FakeDriveService(files=[{"id": "1", "name": "Orçamento 2026.xlsx", "webViewLink": "https://drive.google.com/x"}])
    monkeypatch.setattr(gdrive, "get_google_service", lambda *a, **k: fake)

    result = gdrive.search_drive_files(query="orçamento")

    assert result.success
    assert "Orçamento 2026.xlsx" in result.message


def test_no_google_credentials_result_menciona_o_arquivo_esperado():
    result = no_google_credentials_result()
    assert not result.success
    assert "google_credentials.json" in result.message
