"""
Interface gráfica "web" do Jarvis — uma janela nativa (pywebview) que
renderiza uma página HTML/CSS/JS local (interface_web/web/), em vez do
CustomTkinter usado antes (interface/app.py, mantido como alternativa
de reserva — veja main.py::run_gui_mode).

Motivo da troca: CustomTkinter/Tkinter só desenha formas simples e
cores chapadas — não dá pra fazer o efeito de "brilho"/glow, gradientes
suaves e partículas que o usuário pediu (referência visual dele: um
painel de diagnóstico futurista, estilo ficção científica). Uma página
HTML/CSS/JS de verdade consegue isso nativamente (box-shadow com blur,
gradientes radiais, canvas), então a interface virou uma página local
mostrada dentro de uma janela do sistema operacional, sem precisar de
navegador nem servidor separado.

`interface_web/bridge.py` não importa `pywebview` no topo do arquivo —
só dentro das funções que realmente precisam da janela — assim toda a
lógica de negócio (chat, confirmações, toggles) continua testável neste
projeto mesmo sem o pywebview instalado (o pacote não está disponível
neste ambiente de desenvolvimento; ver comentário em requirements.txt).
"""
