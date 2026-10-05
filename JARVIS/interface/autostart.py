"""
Iniciar o Jarvis sozinho com o Windows — parte de "usar o Jarvis só
como .exe, feito um app de verdade" (junto com o ícone na bandeja em
`interface/tray.py` e a voz contínua direto pela interface).

Usa a chave de registro do PRÓPRIO usuário
(HKEY_CURRENT_USER\\...\\Run) — não precisa de administrador e não
mexe em nada do resto do sistema, só o que abre quando VOCÊ loga no
Windows. Só é oferecido dentro do `Jarvis.exe` já empacotado
(sys.frozen): registrar `python main.py` no lugar do .exe seria frágil
(quebraria se o venv ou o caminho do projeto mudassem de lugar).
"""
from __future__ import annotations

import sys

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "Jarvis"


def supported() -> bool:
    """Início automático só faz sentido no Windows, dentro do .exe empacotado."""
    return sys.platform == "win32" and getattr(sys, "frozen", False)


def _command() -> str:
    # --minimized: abre direto na bandeja, sem popar a janela a cada login
    # (só some de verdade se o ícone da bandeja estiver disponível — ver
    # interface/tray.py e interface/app.py::run_app).
    return f'"{sys.executable}" --minimized'


def is_enabled() -> bool:
    """True se o Jarvis já está cadastrado pra abrir sozinho com o Windows."""
    if not supported():
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, _VALUE_NAME)
    except FileNotFoundError:
        return False
    return value == _command()


def set_enabled(enabled: bool) -> None:
    """
    Liga/desliga o início automático. Levanta RuntimeError com uma
    mensagem amigável se chamado fora do .exe empacotado no Windows —
    a interface gráfica só deve oferecer esse botão quando `supported()`
    for True, mas isso protege contra chamadas diretas também.
    """
    if not supported():
        raise RuntimeError(
            "Início automático com o Windows só está disponível no Jarvis.exe empacotado."
        )
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, _command())
        else:
            try:
                winreg.DeleteValue(key, _VALUE_NAME)
            except FileNotFoundError:
                pass
