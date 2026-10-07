"""Camada de plugins do JARVIS/NEXUS."""

from plugins.base import Plugin, PluginCapability, PluginResult, PluginStatus
from plugins.registry import PluginRegistry, build_default_plugin_registry

__all__ = [
    "Plugin",
    "PluginCapability",
    "PluginResult",
    "PluginStatus",
    "PluginRegistry",
    "build_default_plugin_registry",
]
