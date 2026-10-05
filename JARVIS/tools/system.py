"""
Ferramenta: informações e controle do sistema Windows — seções 15 e 16.

Usa `psutil` para métricas (CPU/RAM/disco/bateria) e tenta `pycaw`
para volume (Windows). Hardware não suportado (ex.: GPU sem
sensores) devolve "N/A" em vez de quebrar o programa.
"""
from __future__ import annotations

import platform
from datetime import datetime

from core.permissions import RiskLevel
from tools.base import Tool, ToolResult
from platform_services import get_platform_services


def get_time(**_: object) -> ToolResult:
    now = datetime.now()
    return ToolResult(success=True, message=f"Agora são {now.strftime('%H:%M')}.", data={"time": now.isoformat()})


def system_status(**_: object) -> ToolResult:
    try:
        import psutil
    except ImportError:
        return ToolResult(success=False, message="A biblioteca psutil não está instalada.")

    cpu = psutil.cpu_percent(interval=0.3)
    mem = psutil.virtual_memory()
    disk_path = "C:\\" if platform.system() == "Windows" else "/"
    disk = psutil.disk_usage(disk_path)

    battery_txt = "N/A"
    try:
        battery = psutil.sensors_battery()
        if battery is not None:
            battery_txt = f"{battery.percent}%" + (" (carregando)" if battery.power_plugged else "")
    except Exception:
        pass

    data = {
        "cpu_percent": cpu,
        "ram_percent": mem.percent,
        "ram_used_gb": round(mem.used / (1024**3), 1),
        "ram_total_gb": round(mem.total / (1024**3), 1),
        "disk_percent": disk.percent,
        "disk_free_gb": round(disk.free / (1024**3), 1),
        "battery": battery_txt,
    }
    message = (
        f"CPU em {cpu:.0f}%, RAM em {mem.percent:.0f}% "
        f"({data['ram_used_gb']}GB de {data['ram_total_gb']}GB), "
        f"disco com {data['disk_free_gb']}GB livres."
    )
    return ToolResult(success=True, message=message, data=data)


def set_volume(level: int, **_: object) -> ToolResult:
    result = get_platform_services().set_volume(level)
    return ToolResult(result.success, result.message, result.data)


def mute_volume(**_: object) -> ToolResult:
    result = get_platform_services().mute_volume()
    return ToolResult(result.success, result.message, result.data)


def lock_computer(**_: object) -> ToolResult:
    result = get_platform_services().lock_session()
    return ToolResult(result.success, result.message, result.data)


def register(registry) -> None:
    registry.register(Tool(
        name="get_time",
        description="Diz a hora atual.",
        parameters={"type": "object", "properties": {}},
        risk_level=RiskLevel.LOW,
        handler=get_time,
    ))
    registry.register(Tool(
        name="system_status",
        description="Consulta o uso de CPU, RAM, disco e bateria do computador em tempo real.",
        parameters={"type": "object", "properties": {}},
        risk_level=RiskLevel.LOW,
        handler=system_status,
    ))
    registry.register(Tool(
        name="set_volume",
        description="Ajusta o volume do sistema para um nível de 0 a 100.",
        parameters={
            "type": "object",
            "properties": {"level": {"type": "integer", "description": "Nível de 0 a 100"}},
            "required": ["level"],
        },
        risk_level=RiskLevel.LOW,
        handler=set_volume,
        confirmation_template="Ajustar volume para {level}%",
    ))
    registry.register(Tool(
        name="mute_volume",
        description="Muta o áudio do sistema.",
        parameters={"type": "object", "properties": {}},
        risk_level=RiskLevel.LOW,
        handler=mute_volume,
    ))
    registry.register(Tool(
        name="lock_computer",
        description="Bloqueia a sessão atual do sistema operacional imediatamente.",
        parameters={"type": "object", "properties": {}},
        risk_level=RiskLevel.HIGH,
        handler=lock_computer,
        confirmation_template="Bloquear o computador agora",
    ))
