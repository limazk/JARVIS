from __future__ import annotations

import threading

from config.settings import settings
from core import background


class FakeAgent:
    def __init__(self, **kwargs): self.shutdown_called = False
    def shutdown(self): self.shutdown_called = True
    def process(self, text, response_mode="text"): return "ok"


class FakeDetector:
    def __init__(self, on_wake): self.on_wake = on_wake; self.started = False; self.stopped = False; self.joined = False
    def start(self): self.started = True
    def stop(self): self.stopped = True
    def join(self): self.joined = True


class FakeRotina:
    def __init__(self): self.started = False; self.stopped = False
    def ensure_running(self): self.started = True
    def stop(self): self.stopped = True


def test_background_starts_wakeword_and_cleans_resources(monkeypatch):
    monkeypatch.setattr(background, "JarvisAgent", FakeAgent)
    monkeypatch.setattr(background, "RotinaProcessManager", FakeRotina)
    monkeypatch.setattr(background.listener, "is_ready", lambda: True)
    monkeypatch.setattr(settings, "wake_word_enabled", True)
    stop = threading.Event()
    stop.set()
    runtime = background.BackgroundRuntime(stop_event=stop, detector_factory=FakeDetector)
    runtime.run(install_signal_handlers=False)
    assert runtime.detector.started and runtime.detector.stopped and runtime.detector.joined
    assert runtime.agent.shutdown_called
    assert runtime.rotina.started and runtime.rotina.stopped


def test_background_dispatch_does_not_initialize_gui(monkeypatch, tmp_path):
    import main

    calls = []
    monkeypatch.setattr(main, "run_background_mode", lambda: calls.append("background"))
    monkeypatch.setattr(main, "run_gui_mode", lambda **kwargs: calls.append("gui"))
    monkeypatch.setattr(settings, "instance_lock_path", tmp_path / "instance.lock")
    monkeypatch.setattr(settings, "log_path", tmp_path / "jarvis.log")
    monkeypatch.setattr("sys.argv", ["main.py", "--background"])
    main.main()
    assert calls == ["background"]


def test_background_prefilled_command_nao_reabre_microfone(monkeypatch):
    """Se a mesma frase já trouxe 'Jarvis, <comando>', o background deve
    processar <comando> diretamente sem falar por cima nem gravar de novo."""
    runtime = background.BackgroundRuntime(
        stop_event=threading.Event(),
        detector_factory=FakeDetector,
    )
    runtime.agent = FakeAgent()

    spoken = []
    processed = []

    monkeypatch.setattr(runtime, "_speak", lambda text: spoken.append(text))
    monkeypatch.setattr(
        runtime.agent,
        "process",
        lambda text, response_mode="text": (
            processed.append((text, response_mode)) or "ok"
        ),
    )
    monkeypatch.setattr(
        background.listener,
        "listen_once",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("não deveria reabrir o microfone")
        ),
    )
    monkeypatch.setattr(
        runtime,
        "_prefetch_rotina_health",
        lambda: None,
    )

    runtime._on_wake("quanto ganhei essa semana")

    assert processed == [("quanto ganhei essa semana", "voice")]
    assert spoken == ["ok"]
