"""Regression tests for the JARVIS shell tool security boundary."""
from types import SimpleNamespace

import pytest

from core.permissions import PermissionManager
from tools import shell as shell_tool
from tools.registry import ToolRegistry


@pytest.mark.parametrize(
    "command",
    [
        "git status; echo injected",
        "git status && echo injected",
        "git status | cat",
        "git status > output.txt",
        "git status\nwhoami",
        "echo $(whoami)",
        "echo $HOME",
        "bash -c whoami",
        "cmd.exe /c dir",
        "sudo git status",
        "shutdown -h now",
        "rm -rf /",
        "git status $(touch injected)",
        "git status " + chr(96) + "whoami" + chr(96),
        "",
        "git status " + ("x" * 4100),
        "git status 'unterminated",
    ],
)
def test_rejects_shell_syntax_and_unsafe_interpreters(command):
    assert shell_tool.classify_command(command) == shell_tool.CommandClass.BLOCKED


@pytest.mark.parametrize(
    "command",
    [
        "git status",
        "git status --short",
        "git diff --check",
        "git log --oneline",
        "git remote -v",
        "ls -la",
        "pip list",
        "pip3 show pytest",
        "npm --version",
        "dir",
        "echo hello",
    ],
)
def test_simple_read_only_commands_are_safe(command):
    assert shell_tool.classify_command(command) == shell_tool.CommandClass.SAFE


@pytest.mark.parametrize(
    "command",
    [
        "python demo.py",
        "node demo.js",
        "pip install requests",
        "git push origin main",
        "git branch -D old-branch",
        "git status --ignored",
        "mv old new",
    ],
)
def test_commands_with_side_effects_require_confirmation(command):
    assert shell_tool.classify_command(command) == shell_tool.CommandClass.CONFIRMATION_REQUIRED


def _registered_tool(permissions):
    registry = ToolRegistry()
    shell_tool.register(registry, permissions=permissions)
    return registry.get("run_shell_command")


def test_without_permission_manager_side_effects_fail_closed(monkeypatch):
    def should_not_run(*args, **kwargs):
        raise AssertionError("Subprocess must not run without approval")

    monkeypatch.setattr(shell_tool.subprocess, "run", should_not_run)
    result = _registered_tool(None).execute(command="python demo.py")
    assert result.success is False
    assert "confirmação" in result.message


def test_denied_command_never_runs(monkeypatch):
    def should_not_run(*args, **kwargs):
        raise AssertionError("Denied command must not run")

    monkeypatch.setattr(shell_tool.subprocess, "run", should_not_run)
    manager = PermissionManager(confirm_callback=lambda _: False)
    result = _registered_tool(manager).execute(command="python demo.py")
    assert result.success is False
    assert "cancelada" in result.message


def test_confirmed_command_uses_shell_false_and_argv(monkeypatch):
    recorded = {}

    def fake_run(argv, **kwargs):
        recorded["argv"] = argv
        recorded.update(kwargs)
        return SimpleNamespace(stdout="ok\n", stderr="", returncode=0)

    monkeypatch.setattr(shell_tool.subprocess, "run", fake_run)
    manager = PermissionManager(confirm_callback=lambda _: True)
    result = _registered_tool(manager).execute(command='python "my script.py"')
    assert result.success
    assert result.message == "ok"
    assert recorded["argv"] == ["python", "my script.py"]
    assert recorded["shell"] is False
    assert recorded["timeout"] == 60


def test_safe_command_runs_without_confirmation(monkeypatch):
    recorded = {"called": 0}

    def fake_run(argv, **kwargs):
        assert argv == ["git", "status"]
        assert kwargs["shell"] is False
        recorded["called"] += 1
        return SimpleNamespace(stdout="clean", stderr="", returncode=0)

    monkeypatch.setattr(shell_tool.subprocess, "run", fake_run)
    result = _registered_tool(PermissionManager(confirm_callback=lambda _: False)).execute(
        command="git status"
    )
    assert result.success
    assert recorded["called"] == 1


def test_direct_run_refuses_shell_operator(monkeypatch):
    def should_not_run(*args, **kwargs):
        raise AssertionError("Never execute a compound command")

    monkeypatch.setattr(shell_tool.subprocess, "run", should_not_run)
    result = shell_tool._run("git status; echo fail")
    assert not result.success


def test_dir_builtin_lists_files_without_using_a_shell(tmp_path, monkeypatch):
    (tmp_path / "file.txt").write_text("ok", encoding="utf-8")
    monkeypatch.setattr(shell_tool.subprocess, "run", lambda *a, **k: 1 / 0)
    result = shell_tool._run(f'dir "{tmp_path}"')
    assert result.success
    assert "file.txt" in result.message
