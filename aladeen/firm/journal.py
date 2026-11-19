"""A journal of finished AI answers, so a failed research can be continued instead of restarted.

``JournalRunner`` wraps any runner. Every answer it gets back from the model is appended to a file in the
research folder. When the same research is tried again, an identical question is answered from the journal
instantly and for free, so the firm picks up at the step that failed.

A question is identified by what is asked (agent, tier, prompts, answer format), not by which model answers it.
If the first attempt failed because a provider ran out of credit, switching provider in Settings and trying
again still reuses everything already written. The same question can be asked more than once in a research
(a recheck, say) and may deserve a new answer each time, so the nth time it is asked is matched with the nth
answer saved for it.
"""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

JOURNAL_FILE = "journal.jsonl"


def _key(kind: str, name: str, tier: str, system: str, user: str, schema: str = "") -> str:
    blob = json.dumps([kind, name, tier, schema, system, user], ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class JournalRunner:
    """Records every answer of ``inner`` and replays it when the same question comes again."""

    def __init__(self, inner: Any, path: str | Path):
        self.inner = inner
        self.path = Path(path)
        self.replayed = 0  # answers served from the journal during this attempt
        self._lock = threading.Lock()
        self._seen: dict[str, dict] = {}
        self._asked: dict[str, int] = {}  # how many times each question has been asked in this attempt
        self._load()

    # -------------------------------------------------------------- journal file
    def _load(self) -> None:
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
                self._seen[e["key"]] = e
            except (ValueError, KeyError):
                continue  # a half-written last line from a crash: that answer is simply asked again

    @property
    def restored(self) -> int:
        """How many answers were found in the journal when this attempt started."""
        return len(self._seen)

    def _append(self, entry: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._seen[entry["key"]] = entry
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _ask(self, key: str) -> tuple[str, dict | None]:
        """The journal slot for this asking of the question, and the saved answer if there is one."""
        with self._lock:
            n = self._asked.get(key, 0)
            self._asked[key] = n + 1
            slot = f"{key}:{n}"
            e = self._seen.get(slot)
            if e is not None:
                self.replayed += 1
            return slot, e

    # -------------------------------------------------------------- Runner interface
    @property
    def calls(self) -> list[dict]:
        return getattr(self.inner, "calls", [])

    def text(self, system: str, user: str, *, tier: str = "quick", name: str = "") -> str:
        slot, hit = self._ask(_key("text", name, tier, system, user))
        if hit is not None:
            return hit["text"]
        out = self.inner.text(system, user, tier=tier, name=name)
        self._append({"key": slot, "kind": "text", "name": name, "tier": tier, "text": out})
        return out

    def structured(self, system: str, user: str, schema: type[T], *, tier: str = "quick", name: str = "") -> T:
        slot, hit = self._ask(_key("structured", name, tier, system, user, schema.__name__))
        if hit is not None:
            try:
                return schema.model_validate(hit["data"])
            except ValueError:
                with self._lock:  # the schema changed since: ask again rather than fail
                    self._seen.pop(slot, None)
                    self.replayed -= 1
        out = self.inner.structured(system, user, schema, tier=tier, name=name)
        self._append({"key": slot, "kind": "structured", "name": name, "tier": tier, "schema": schema.__name__,
                      "data": out.model_dump(mode="json")})
        return out
