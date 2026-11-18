"""Live event stream of a research run (what each agent is doing), consumed by the dashboard."""

from __future__ import annotations

import threading
import time
from typing import Any


class EventLog:
    def __init__(self):
        self._events: list[dict[str, Any]] = []
        self._cond = threading.Condition()
        self.closed = False

    def emit(self, type_: str, **kw: Any) -> dict:
        with self._cond:
            ev = {"seq": len(self._events), "ts": time.time(), "type": type_, **kw}
            self._events.append(ev)
            if type_ in ("done", "error"):
                self.closed = True
            self._cond.notify_all()
            return ev

    def since(self, seq: int, timeout: float = 15.0) -> list[dict]:
        """Events with sequence >= seq; waits up to ``timeout`` seconds for new ones."""
        with self._cond:
            if seq >= len(self._events) and not self.closed:
                self._cond.wait(timeout)
            return list(self._events[seq:])

    def all(self) -> list[dict]:
        with self._cond:
            return list(self._events)

    # convenience wrappers ------------------------------------------------
    def phase(self, phase: str, status: str = "active") -> None:
        self.emit("phase", phase=phase, status=status)

    def agent(self, agent: str, status: str, task: str = "") -> None:
        self.emit("agent", agent=agent, status=status, task=task)

    def message(self, frm: str, to: str, text: str) -> None:
        self.emit("message", agent=frm, to=to, text=text)

    def log(self, agent: str, text: str, detail: str = "") -> None:
        self.emit("log", agent=agent, text=text, detail=detail[:1200])


class NullLog(EventLog):
    """Used when nobody is watching (headless runs, tests)."""
