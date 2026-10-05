"""Renderização testável da unidade systemd."""
from __future__ import annotations

from pathlib import Path


def render_service(template: str, project_dir: Path, python_path: Path) -> str:
    project = str(project_dir.resolve())
    python = str(python_path.resolve())
    if "\n" in project or "\n" in python:
        raise ValueError("Caminho inválido para unidade systemd.")
    return template.replace("@PROJECT_DIR@", project).replace("@PYTHON@", python)
