"""
Cria a janela pywebview de verdade e conecta o WebBridge a ela.

Este módulo (ao contrário de interface_web/bridge.py) importa
`webview` de propósito — é exatamente por isso que fica separado num
arquivo à parte: `main.py::run_gui_mode` importa este módulo dentro de
um try/except ImportError, então uma máquina sem o pacote `pywebview`
instalado (ou sem o WebView2 Runtime, no Windows) cai sozinha de volta
para a interface antiga em CustomTkinter (interface/app.py), sem que a
pessoa precise fazer nada — mesma filosofia de "degradar graciosamente"
usada em todo o resto do projeto (pystray, openwakeword, etc.).

*** Aviso importante para quem for mexer aqui ***
Não foi possível instalar nem executar o pywebview no ambiente onde
este arquivo foi escrito (sem acesso ao índice do PyPI — ver o
comentário em requirements.txt), então este arquivo foi escrito e
revisado com base só na documentação oficial do projeto
(https://pywebview.flowrl.com/), sem poder testar a janela abrindo de
verdade. A lógica de negócio de verdade (chat, permissões, automação)
mora inteira em interface_web/bridge.py, que É testado — este arquivo
é só "encanamento" da janela, do mesmo jeito que
interface/app.py::run_app() também nunca foi (nem podia ser) testado
automaticamente neste projeto. Teste manual no Windows antes de
confiar de olhos fechados, principalmente a linha marcada abaixo sobre
o evento "closing".
"""
from __future__ import annotations

import threading
from pathlib import Path

from config.settings import settings

_WEB_DIR = Path(__file__).resolve().parent / "web"


def run_app(minimized: bool = False) -> None:
    import webview

    from interface_web.bridge import WebBridge

    bridge = WebBridge()

    window = webview.create_window(
        settings.jarvis_name.upper(),
        url=str(_WEB_DIR / "index.html"),
        js_api=bridge,
        width=1280,
        height=800,
        min_size=(980, 640),
        background_color="#000000",
        hidden=minimized,
    )
    bridge.attach_window(window)

    # O evento "closing" do pywebview permite cancelar o fechamento da
    # janela devolvendo False do handler — usado aqui pra replicar o
    # comportamento "X só minimiza pra bandeja" do CustomTkinter
    # (interface/app.py::on_close). Ver o aviso no topo do arquivo:
    # este é o ponto de maior risco deste módulo por não ter sido
    # testado ao vivo.
    window.events.closing += bridge.on_window_closing

    # A bandeja precisa da janela já criada (pra restaurar/mostrar), por
    # isso só é iniciada depois do create_window acima, nunca dentro do
    # __init__ do WebBridge.
    if minimized:
        # Sem bandeja disponível (pystray não instalado), não faz sentido
        # abrir escondido — a pessoa nunca conseguiria abrir de novo.
        threading.Thread(target=bridge.start_tray, daemon=False).start()

        def _check_tray_after_start() -> None:
            import time

            time.sleep(1.0)
            if bridge._tray is None:
                try:
                    window.show()
                except Exception:  # noqa: BLE001
                    pass

        threading.Thread(target=_check_tray_after_start, daemon=True).start()
    else:
        bridge.start_tray()

    webview.start()


def available() -> bool:
    """
    True se dá pra tentar abrir a interface pywebview neste computador
    (pacote instalado) — `main.py::run_gui_mode` usa isso pra decidir
    entre esta interface e a antiga em CustomTkinter, sem precisar
    chegar a criar uma janela só pra descobrir que falhou.
    """
    try:
        import webview  # noqa: F401
    except ImportError:
        return False
    return True
