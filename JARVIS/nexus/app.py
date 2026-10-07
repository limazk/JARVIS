"""Interface TUI real do NEXUS, executada dentro do projeto JARVIS."""
from __future__ import annotations

import curses
import locale
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass, field

from nexus import __version__
from nexus.runtime import NexusRuntime, RunResult


@dataclass
class ConfirmationRequest:
    message: str
    approved: bool | None = None
    done: threading.Event = field(default_factory=threading.Event)


class NexusApp:
    def __init__(self, stdscr) -> None:
        self.stdscr = stdscr
        self.events: queue.Queue = queue.Queue()
        self.logs = deque(maxlen=300)
        self.output = deque(maxlen=500)
        self.input_text = ""
        self.running = True
        self.busy = False
        self.show_result = False
        self.pending_confirmation: ConfirmationRequest | None = None
        self.progress = 0.0
        self.current_prompt = ""
        self.current_provider = "-"
        self.current_kind = "-"
        self.last_result: RunResult | None = None
        self.agent_states = {
            "planner": ("aguardando", "", "-"),
            "router": ("aguardando", "", "-"),
            "worker": ("aguardando", "", "-"),
            "jarvis": ("aguardando", "", "jarvis"),
            "reviewer": ("aguardando", "", "-"),
        }
        self._setup_curses()
        self.runtime = NexusRuntime(
            confirm_callback=self._confirm,
            on_event=lambda a, s, m, p: self.events.put(("agent", (a, s, m, p))),
            on_output=lambda line: self.events.put(("output", line)),
        )
        self.log("nexus", f"NEXUS v{__version__} integrado ao JARVIS. /help para comandos.")

    def _setup_curses(self) -> None:
        locale.setlocale(locale.LC_ALL, "")
        curses.noecho()
        curses.cbreak()
        self.stdscr.keypad(True)
        self.stdscr.timeout(80)
        try:
            curses.curs_set(1)
        except curses.error:
            pass
        if curses.has_colors():
            curses.start_color()
            try:
                curses.use_default_colors()
            except curses.error:
                pass
            for pid, color in (
                (1, curses.COLOR_CYAN),
                (2, curses.COLOR_BLUE),
                (3, curses.COLOR_MAGENTA),
                (4, curses.COLOR_GREEN),
                (5, curses.COLOR_YELLOW),
                (6, curses.COLOR_RED),
                (7, curses.COLOR_WHITE),
            ):
                try:
                    curses.init_pair(pid, color, -1)
                except curses.error:
                    pass

    def color(self, pair: int, bold: bool = False) -> int:
        attr = curses.color_pair(pair) if curses.has_colors() else 0
        return attr | (curses.A_BOLD if bold else 0)

    def safe_add(self, y: int, x: int, text: str, attr: int = 0, width: int | None = None) -> None:
        h, w = self.stdscr.getmaxyx()
        if y < 0 or y >= h or x < 0 or x >= w:
            return
        maxw = max(0, min(width if width is not None else w - x - 1, w - x - 1))
        if maxw <= 0:
            return
        try:
            self.stdscr.addnstr(y, x, str(text).replace("\t", "    "), maxw, attr)
        except curses.error:
            pass

    def box(self, y: int, x: int, h: int, w: int, title: str, pair: int = 2) -> None:
        if h < 3 or w < 8:
            return
        attr = self.color(pair)
        self.safe_add(y, x, "╭" + "─" * (w - 2) + "╮", attr, w)
        for yy in range(y + 1, y + h - 1):
            self.safe_add(yy, x, "│", attr, 1)
            self.safe_add(yy, x + w - 1, "│", attr, 1)
        self.safe_add(y + h - 1, x, "╰" + "─" * (w - 2) + "╯", attr, w)
        self.safe_add(y, x + 2, f" {title} ", self.color(pair, True), max(0, w - 4))

    def log(self, actor: str, message: str, pair: int = 7) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.logs.append((stamp, actor, message, pair))

    def _confirm(self, message: str) -> bool:
        request = ConfirmationRequest(message=message)
        self.events.put(("confirm", request))
        if not request.done.wait(timeout=180):
            return False
        return request.approved is True

    def _start_task(self, prompt: str) -> None:
        if self.busy:
            self.log("nexus", "Já existe uma tarefa em execução.", 5)
            return
        self.busy = True
        self.current_prompt = prompt
        self.current_provider = "-"
        self.current_kind = "-"
        self.progress = 0.03
        self.output.clear()

        def worker() -> None:
            result = self.runtime.execute(prompt)
            self.events.put(("done", result))

        threading.Thread(target=worker, daemon=True).start()

    def _process_events(self) -> None:
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                return

            if kind == "output":
                self.output.append(str(payload))
            elif kind == "confirm":
                self.pending_confirmation = payload
                self.log("permissão", payload.message, 5)
            elif kind == "agent":
                actor, state, message, provider = payload
                self.agent_states[actor] = (state, message, provider or "-")
                if provider:
                    self.current_provider = provider
                self.current_kind = self.current_kind if self.current_kind != "-" else state
                self.log(actor, f"{state}: {message}" if message else state, self._state_color(state))
                if actor == "planner":
                    self.progress = max(self.progress, 0.12)
                elif actor == "router":
                    self.progress = max(self.progress, 0.30)
                elif actor in {"worker", "jarvis"}:
                    self.progress = max(self.progress, 0.62)
                elif actor == "reviewer" and state == "revisando":
                    self.progress = max(self.progress, 0.90)
                elif state == "concluído":
                    self.progress = 1.0
            elif kind == "done":
                self.last_result = payload
                self.busy = False
                self.current_provider = payload.provider
                self.current_kind = payload.kind
                self.progress = 1.0 if payload.ok else self.progress
                self.log(
                    "nexus",
                    f"{'Concluído' if payload.ok else 'Falhou'} via {payload.provider} em {payload.elapsed:.1f}s",
                    4 if payload.ok else 6,
                )

    @staticmethod
    def _state_color(state: str) -> int:
        state = state.lower()
        if "erro" in state:
            return 6
        if "conclu" in state:
            return 4
        if "revis" in state:
            return 5
        if state in {"planejando", "roteando", "fallback"}:
            return 3
        if "execut" in state:
            return 1
        return 7

    def command(self, text: str) -> None:
        cmd = text.strip()
        if not cmd:
            return
        if cmd == "/quit":
            self.running = False
        elif cmd == "/clear":
            self.logs.clear()
            self.output.clear()
        elif cmd == "/result":
            self.show_result = not self.show_result
        elif cmd == "/demo":
            self.runtime.demo = not self.runtime.demo
            self.log("nexus", f"Modo demo: {'ON' if self.runtime.demo else 'OFF'}", 5)
        elif cmd == "/refresh":
            self.runtime.refresh()
            self.log("nexus", "Providers reescaneados.", 4)
        elif cmd == "/providers":
            self.runtime.refresh()
            self.log("provider", "JARVIS interno: disponível", 4)
            for provider in self.runtime.providers.values():
                self.log(
                    "provider",
                    f"{provider.label}: {'disponível' if provider.available else 'offline'} ({provider.model})",
                    4 if provider.available else 6,
                )
        elif cmd == "/help":
            self.log("nexus", "/providers /refresh /demo /result /clear /quit", 1)
        else:
            self._start_task(cmd)

    def handle_key(self, ch) -> None:
        if self.pending_confirmation is not None:
            if isinstance(ch, str):
                key = ch.lower()
            else:
                key = ""
            if key in {"s", "y"}:
                self.pending_confirmation.approved = True
                self.pending_confirmation.done.set()
                self.pending_confirmation = None
            elif key in {"n"} or ch == 27:
                self.pending_confirmation.approved = False
                self.pending_confirmation.done.set()
                self.pending_confirmation = None
            return

        if ch in ("\n", "\r", curses.KEY_ENTER, 10, 13):
            text = self.input_text.strip()
            self.input_text = ""
            if text:
                self.command(text)
            return
        if ch in (27,):
            self.input_text = ""
            return
        if ch in (curses.KEY_BACKSPACE, 127, 8, "\b", "\x7f"):
            self.input_text = self.input_text[:-1]
            return
        if ch in ("\x03", 3):
            if self.busy:
                self.log("nexus", "Tarefa em execução; use /quit após concluir ou aguarde.", 5)
            else:
                self.running = False
            return
        if isinstance(ch, str) and ch.isprintable():
            self.input_text += ch

    def draw_header(self, w: int) -> int:
        logo = (
            "      ✦       ╲       ╱",
            "   ╲  │  ╱     ╲  ✦ ╱",
            " ───  ★  ───    ╲ ╱      N E X U S",
            "   ╱  │  ╲       ✦",
        )
        for i, line in enumerate(logo):
            self.safe_add(i, 2, line, self.color(3 if i % 2 else 1, True), min(w - 4, 48))
        if w >= 90:
            self.safe_add(1, 52, "Orquestrador multiagente integrado ao JARVIS", self.color(7, True), w - 54)
            self.safe_add(2, 52, "PLANEJA › DELEGA › EXECUTA › ENTREGA", self.color(1, True), w - 54)
            self.safe_add(3, 52, "Memória + Tools + ROTINA + Workers externos", self.color(7), w - 54)
        return 5

    def draw_system(self, y: int, x: int, h: int, w: int) -> None:
        self.box(y, x, h, w, "SISTEMA", 2)
        rows = [("JARVIS", True, "núcleo interno")]
        rows += [(p.label, p.available, p.model) for p in self.runtime.providers.values()]
        for i, (name, ok, detail) in enumerate(rows[: h - 2]):
            yy = y + 1 + i
            self.safe_add(yy, x + 2, "●", self.color(4 if ok else 6, True), 2)
            self.safe_add(yy, x + 4, f"{name:<11}", self.color(7, True), 12)
            self.safe_add(yy, x + 16, "online" if ok else "offline", self.color(4 if ok else 6), 9)
            self.safe_add(yy, x + 26, detail, self.color(7), max(0, w - 28))

    def draw_agents(self, y: int, x: int, h: int, w: int) -> None:
        self.box(y, x, h, w, "AGENTES", 3)
        names = (
            ("planner", "Planner"),
            ("router", "Router"),
            ("worker", "Worker"),
            ("jarvis", "Jarvis"),
            ("reviewer", "Reviewer"),
        )
        for i, (key, label) in enumerate(names[: h - 2]):
            state, message, provider = self.agent_states.get(key, ("aguardando", "", "-"))
            yy = y + 1 + i
            pair = self._state_color(state)
            self.safe_add(yy, x + 2, f"● {label:<10}", self.color(pair, True), 13)
            self.safe_add(yy, x + 15, f"{state:<12}", self.color(pair), 12)
            self.safe_add(yy, x + 28, message or provider, self.color(7), max(0, w - 30))

    def draw_execution(self, y: int, x: int, h: int, w: int) -> None:
        self.box(y, x, h, w, "EXECUÇÃO", 2)
        task = self.current_prompt or "Aguardando tarefa"
        self.safe_add(y + 1, x + 2, f"Tarefa: {task}", self.color(1, True), w - 4)
        self.safe_add(y + 2, x + 2, f"Provider: {self.current_provider}  Tipo: {self.current_kind}", self.color(7), w - 4)
        inner = max(8, w - 12)
        filled = int(inner * max(0.0, min(1.0, self.progress)))
        bar = "█" * filled + "░" * (inner - filled)
        self.safe_add(y + h - 3, x + 2, bar, self.color(3), inner)
        self.safe_add(y + h - 3, x + 3 + inner, f"{int(self.progress * 100):>3}%", self.color(7), 4)
        status = "PROCESSANDO" if self.busy else "PRONTO"
        self.safe_add(y + h - 2, x + 2, status, self.color(5 if self.busy else 4, True), w - 4)

    def draw_logs(self, y: int, x: int, h: int, w: int) -> None:
        self.box(y, x, h, w, "RESULTADO" if self.show_result else "LOGS", 2)
        if self.show_result:
            lines = list(self.output)[-max(0, h - 2):]
            for i, line in enumerate(lines):
                self.safe_add(y + 1 + i, x + 2, line, self.color(7), w - 4)
        else:
            rows = list(self.logs)[-max(0, h - 2):]
            for i, (stamp, actor, message, pair) in enumerate(rows):
                prefix = f"[{stamp}] {actor:<9} › "
                self.safe_add(y + 1 + i, x + 2, prefix, self.color(pair, True), min(len(prefix), w - 4))
                self.safe_add(y + 1 + i, x + 2 + len(prefix), message, self.color(7), max(0, w - 4 - len(prefix)))

    def draw_history(self, y: int, x: int, h: int, w: int) -> None:
        self.box(y, x, h, w, "TRABALHOS RECENTES", 3)
        try:
            rows = self.runtime.recent_jobs(max(1, h - 2))
        except Exception:
            rows = []
        for i, row in enumerate(rows[: h - 2]):
            status = row.get("status", "")
            pair = 4 if status == "concluído" else 6 if status == "erro" else 1
            text = f"#{row.get('id')} {str(row.get('prompt',''))[:25]} · {row.get('provider','-')}"
            self.safe_add(y + 1 + i, x + 2, text, self.color(pair if i == 0 else 7), w - 4)

    def draw_input(self, h: int, w: int) -> None:
        y = h - 3
        self.safe_add(y, 1, "NEXUS ❯", self.color(3, True), 8)
        x = 10
        width = max(8, w - x - 2)
        self.safe_add(y, x, " " * width, curses.A_REVERSE, width)
        visible = self.input_text[-(width - 2):]
        placeholder = "descreva sua tarefa... (/help)"
        self.safe_add(y, x + 1, visible or placeholder, curses.A_DIM if not visible else 0, width - 2)
        self.safe_add(h - 2, 1, "Enter enviar · /result saída · /providers status · Ctrl+C sair", self.color(7), w - 3)
        try:
            self.stdscr.move(y, min(w - 2, x + 1 + len(visible)))
        except curses.error:
            pass

    def draw_confirmation(self, h: int, w: int) -> None:
        if self.pending_confirmation is None:
            return
        box_w = min(86, max(50, w - 12))
        box_h = 7
        y = max(1, (h - box_h) // 2)
        x = max(1, (w - box_w) // 2)
        self.box(y, x, box_h, box_w, "CONFIRMAÇÃO DO JARVIS", 5)
        message = self.pending_confirmation.message
        first = message[: box_w - 6]
        second = message[box_w - 6 : 2 * (box_w - 6)]
        self.safe_add(y + 2, x + 3, first, self.color(7), box_w - 6)
        self.safe_add(y + 3, x + 3, second, self.color(7), box_w - 6)
        self.safe_add(y + 5, x + 3, "[S] Sim     [N] Não", self.color(5, True), box_w - 6)

    def draw(self) -> None:
        self.stdscr.erase()
        h, w = self.stdscr.getmaxyx()
        if h < 22 or w < 80:
            self.safe_add(1, 2, "NEXUS", self.color(3, True))
            self.safe_add(3, 2, "Terminal pequeno. Mínimo: 80x22. Recomendado: 120x32.", self.color(6, True), w - 4)
            self.draw_input(h, w)
            self.stdscr.refresh()
            return

        top = self.draw_header(w)
        bottom = h - 4
        top_h = min(9, max(7, (bottom - top) // 3))

        if w >= 120:
            a = int(w * 0.31)
            b = int(w * 0.33)
            c = w - a - b
            self.draw_system(top, 0, top_h, a)
            self.draw_agents(top, a, top_h, b)
            self.draw_execution(top, a + b, top_h, c)
        else:
            half = w // 2
            self.draw_agents(top, 0, top_h, half)
            self.draw_execution(top, half, top_h, w - half)

        lower_y = top + top_h
        lower_h = bottom - lower_y
        if w >= 105:
            logs_w = int(w * 0.68)
            self.draw_logs(lower_y, 0, lower_h, logs_w)
            self.draw_history(lower_y, logs_w, lower_h, w - logs_w)
        else:
            self.draw_logs(lower_y, 0, lower_h, w)

        self.draw_input(h, w)
        self.draw_confirmation(h, w)
        self.stdscr.refresh()

    def run(self) -> None:
        try:
            while self.running:
                self._process_events()
                self.draw()
                try:
                    ch = self.stdscr.get_wch()
                except curses.error:
                    continue
                self.handle_key(ch)
        finally:
            if self.pending_confirmation is not None:
                self.pending_confirmation.approved = False
                self.pending_confirmation.done.set()
            self.runtime.shutdown()


def launch() -> None:
    curses.wrapper(lambda stdscr: NexusApp(stdscr).run())
