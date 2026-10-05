"""
Ícone na bandeja do Windows (systray) — parte de "usar o Jarvis só como
.exe, feito um app de verdade": fechar a janela não encerra mais o
Jarvis, só minimiza pra bandeja (igual WhatsApp/Discord/Spotify),
continuando a rodar em segundo plano — o que também é o que faz a voz
contínua e o início automático com o Windows (`interface/autostart.py`)
fazerem sentido na prática.

Requer o pacote opcional `pystray` (ver requirements.txt). Sem ele
instalado, o Jarvis funciona normalmente — só que fechar a janela
encerra o programa de verdade, como antes desta funcionalidade.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

from config.settings import settings

logger = logging.getLogger("jarvis.interface.tray")


class TrayIcon:
    def __init__(self, on_open: Callable[[], None], on_quit: Callable[[], None]) -> None:
        self._on_open = on_open
        self._on_quit = on_quit
        self._icon = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> bool:
        """
        Sobe o ícone na bandeja em segundo plano. Retorna False (sem
        levantar exceção) se `pystray`/Pillow não estiverem instalados
        ou o ícone não puder ser carregado — quem chama decide o que
        fazer nesse caso (deixar a janela fechar de verdade, por exemplo).
        """
        try:
            import pystray
            from PIL import Image
        except ImportError as exc:
            logger.info("pystray/Pillow indisponível (%s) — sem ícone na bandeja.", exc)
            return False

        icon_path = settings.base_dir / "assets" / "logo_mark.png"
        try:
            image = Image.open(icon_path)
        except Exception as exc:
            logger.warning("Não consegui carregar o ícone da bandeja (%s).", exc)
            return False

        menu = pystray.Menu(
            pystray.MenuItem("Abrir Jarvis", lambda: self._on_open(), default=True),
            pystray.MenuItem("Sair", lambda: self._on_quit()),
        )
        self._icon = pystray.Icon(settings.jarvis_name, image, settings.jarvis_name, menu)
        self._thread = threading.Thread(target=self._icon.run, daemon=True, name="jarvis-tray")
        self._thread.start()
        return True

    def stop(self) -> None:
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:  # noqa: BLE001
                pass
            self._icon = None
