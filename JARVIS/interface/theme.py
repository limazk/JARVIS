"""
Paleta visual do Jarvis — baseada na logo oficial (estrela roxa/branca
sobre fundo preto, `assets/logo_mark.png` / `assets/logo_wordmark.png`).

Cores extraídas diretamente da logo (não "chutadas"): o roxo vivo é o
mesmo do bloco sólido atrás de "VIS" no wordmark, o roxo escuro é a
média dos traços de contorno da estrela, e o lilás claro é a média dos
pixels de brilho/glow ao redor dela. Um só arquivo com essas constantes
em vez de cada componente da interface ter seu próprio hex espalhado —
troque aqui se um dia quiser ajustar a paleta inteira de uma vez.
"""
from __future__ import annotations

BG = "#000000"           # fundo principal — preto igual ao da logo
PANEL = "#0d0d12"         # painéis/cards (levemente mais claro que o fundo puro)
SURFACE = "#1b1b22"       # campos de entrada, caixas de texto
SURFACE_HOVER = "#2a2a33"  # hover de botões "neutros" (cancelar, configurações)

PURPLE = "#6232DD"        # roxo vivo — mesmo tom do bloco sólido "VIS" da logo
PURPLE_HOVER = "#7B42E8"  # variação um pouco mais clara, para hover de botões
PURPLE_LIGHT = "#B891F8"  # lilás claro (glow da estrela) — estados "ativo"/sucesso
PURPLE_DARK = "#280A99"   # roxo escuro (traço/contorno da estrela) — bordas, detalhes

TEXT = "#F5F5F7"          # texto principal (quase branco, como o "JAR" da logo)
TEXT_DIM = "#9C93B5"      # texto secundário (cinza com leve tom roxo)

ERROR = "#EF4444"         # vermelho de erro — não vem da logo, mas é universal
OK = "#3DDC84"            # verde de "módulo configurado/ok" — só usado como pontinho
                          # de status ao lado de um módulo, nunca em texto/botão grande
                          # (a paleta da marca continua sendo só preto/roxo)

BORDER = "#2A2A38"        # contorno fino dos cards do painel "Visão geral"
BORDER_ACCENT = "#3D2A70" # variação do contorno com um pouco mais de roxo, pro card
                          # em destaque (o "núcleo" do Jarvis) se diferenciar dos demais
