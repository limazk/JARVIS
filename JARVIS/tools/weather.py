"""
Previsão do tempo — seção 24 do spec.

Usa wttr.in, uma API pública e gratuita que não exige cadastro nem
chave — funciona só com uma requisição HTTP simples. Se
OPENWEATHER_API_KEY estiver configurada no .env, dá para trocar por
OpenWeatherMap no futuro sem mudar a assinatura desta ferramenta
(mesma estrutura de dados de saída).

A cidade padrão vem de WEATHER_CITY no .env/config.
"""
from __future__ import annotations

import requests

from config.settings import settings
from core.permissions import RiskLevel
from tools.base import Tool, ToolResult


def get_weather(day: str = "hoje", city: str = "", **_: object) -> ToolResult:
    target_city = city or settings.weather_city
    try:
        resp = requests.get(f"https://wttr.in/{target_city}", params={"format": "j1"}, timeout=8)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return ToolResult(success=False, message=f"Não consegui consultar a previsão do tempo agora ({exc}).")

    try:
        if day.strip().lower() in {"amanha", "amanhã", "tomorrow"} and len(data["weather"]) > 1:
            forecast = data["weather"][1]
            desc = forecast["hourly"][4]["weatherDesc"][0]["value"]
            max_temp = forecast["maxtempC"]
            min_temp = forecast["mintempC"]
            chance_rain = forecast["hourly"][4].get("chanceofrain", "0")
            message = (
                f"Amanhã em {target_city}: {desc.lower()}, entre {min_temp}°C e {max_temp}°C, "
                f"{chance_rain}% de chance de chuva."
            )
        else:
            current = data["current_condition"][0]
            desc = current["weatherDesc"][0]["value"]
            temp = current["temp_C"]
            feels = current["FeelsLikeC"]
            message = f"Agora em {target_city}: {desc.lower()}, {temp}°C (sensação de {feels}°C)."
    except (KeyError, IndexError) as exc:
        return ToolResult(success=False, message=f"Recebi uma resposta inesperada do serviço de clima ({exc}).")

    return ToolResult(success=True, message=message, data=data.get("current_condition", [{}])[0])


def register(registry) -> None:
    registry.register(Tool(
        name="get_weather",
        description="Consulta a previsão do tempo atual ou de amanhã para a cidade configurada (ou informada).",
        parameters={
            "type": "object",
            "properties": {
                "day": {"type": "string", "description": "'hoje' ou 'amanhã'"},
                "city": {"type": "string", "description": "Cidade, opcional — usa a padrão se vazio"},
            },
        },
        risk_level=RiskLevel.LOW,
        handler=get_weather,
    ))
