"""Testes do App Launcher (tools/apps.py) — seção 12 do spec."""
import platform

from memory.memory import remember_fact
from tools.apps import _resolve_versioned_path, _strip_possessive, open_application
from tools.browser import KNOWN_WEBSITES


def test_programa_desconhecido_retorna_erro_honesto():
    result = open_application(app_name="programa-que-nao-existe-xyz-123")
    assert result.success is False


def test_site_conhecido_esta_no_dicionario_de_aliases():
    assert "github" in KNOWN_WEBSITES
    assert KNOWN_WEBSITES["github"].startswith("https://")


def test_abrir_no_linux_procura_binario_e_nao_finge_sucesso():
    if platform.system() == "Windows":
        return  # este teste é sobre o comportamento em outros SOs
    result = open_application(app_name="chrome")
    assert result.success is False
    assert "não está instalado" in result.message.lower() or "não consegui" in result.message.lower()


def test_resolucao_via_memoria_de_longo_prazo():
    # Seção 29 do spec: "lembra que meu editor é o VS Code" -> depois
    # "abre meu editor" deve entender que é o VS Code.
    remember_fact(fact="meu editor é o VS Code")
    result = open_application(app_name="meu editor")
    # Fora do Windows a abertura em si falha, mas a MENSAGEM deve mostrar
    # que ele resolveu para "vs code" (não para o erro genérico de app desconhecido).
    assert "vs code" in result.message.lower() or result.success is True


def test_strip_possessive():
    assert _strip_possessive("meu github") == "github"
    assert _strip_possessive("minha calculadora") == "calculadora"
    assert _strip_possessive("github") is None  # sem possessivo -> None


def test_abre_meu_github_resolve_como_site_conhecido():
    # Bug conhecido corrigido: "abre meu github" (com possessivo) deve
    # resolver pro mesmo lugar que "abre o github" — sem precisar que o
    # usuário primeiro "ensine" isso via memória.
    result = open_application(app_name="meu github")
    if platform.system() != "Windows":
        # Fora do Windows, o que importa é que ele tentou abrir o site (não
        # caiu no erro genérico de "não encontrei o programa").
        assert "não encontrei" not in result.message.lower()
    else:
        assert result.success is True


def test_resolve_versioned_path_sem_pasta_de_versao_retorna_original(tmp_path):
    # Caminho que não existe e não segue o padrão "app-<versão>" -> devolve
    # o mesmo caminho (deixa o erro real de "arquivo não encontrado" aparecer).
    fake = str(tmp_path / "ProgramaQualquer" / "programa.exe")
    assert _resolve_versioned_path(fake) == fake


def test_resolve_versioned_path_acha_versao_mais_recente(tmp_path):
    # Simula o caso do Discord: a versão configurada (app-1.0.1) não existe
    # mais, mas uma mais nova (app-1.0.9257) está no mesmo lugar.
    (tmp_path / "app-1.0.1").mkdir()
    newer = tmp_path / "app-1.0.9257"
    newer.mkdir()
    (newer / "Discord.exe").write_text("fake exe")

    caminho_antigo = str(tmp_path / "app-1.0.1" / "Discord.exe")
    resolvido = _resolve_versioned_path(caminho_antigo)
    assert resolvido == str(newer / "Discord.exe")
