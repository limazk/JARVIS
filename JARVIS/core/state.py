"""
Estados possíveis do agente Jarvis.

A interface (e os modos texto/voz) usam este enum para saber o que
mostrar ao usuário a cada momento: se está ouvindo, pensando,
executando uma ferramenta, falando, etc. (seção 36 do spec).
"""
from enum import Enum


class AgentState(str, Enum):
    OFFLINE = "OFFLINE"        # ainda não iniciou
    ONLINE = "ONLINE"          # ligado, aguardando comando
    LISTENING = "LISTENING"    # ouvindo o microfone
    PROCESSING = "PROCESSING"  # interpretando a intenção
    EXECUTING = "EXECUTING"    # rodando uma ferramenta
    SPEAKING = "SPEAKING"      # falando a resposta
    ERROR = "ERROR"            # algo deu errado (não derruba o app)
