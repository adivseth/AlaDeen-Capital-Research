"""Shared HTTP session with polite retries and a small on-disk cache."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import requests

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36 aladeen-research-agents"
)


class DataUnavailable(RuntimeError):
    """Raised when a source cannot provide the requested data."""


class Http:
    def __init__(self, cache_dir: str | None = None, timeout: int = 30, ttl_hours: float = 12):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-IN,en;q=0.9"})
        self.timeout = timeout
        self.ttl = ttl_hours * 3600
        self.cache_dir = Path(cache_dir) / "http" if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, url: str, suffix: str) -> Path | None:
        if not self.cache_dir:
            return None
        return self.cache_dir / (hashlib.sha1(url.encode()).hexdigest() + suffix)

    def get(self, url: str, *, binary: bool = False, use_cache: bool = True, retries: int = 3):
        suffix = ".bin" if binary else ".txt"
        cp = self._cache_path(url, suffix)
        if use_cache and cp and cp.exists() and time.time() - cp.stat().st_mtime < self.ttl:
            return cp.read_bytes() if binary else cp.read_text(encoding="utf-8")
        last_err: Exception | None = None
        for attempt in range(retries):
            try:
                r = self.session.get(url, timeout=self.timeout)
                if r.status_code == 429:
                    time.sleep(2 * (attempt + 1))
                    continue
                if r.status_code >= 400:
                    raise DataUnavailable(f"HTTP {r.status_code} for {url}")
                data = r.content if binary else r.text
                if cp:
                    if binary:
                        cp.write_bytes(data)
                    else:
                        cp.write_text(data, encoding="utf-8")
                return data
            except DataUnavailable:
                raise
            except requests.RequestException as e:  # network error: retry
                last_err = e
                time.sleep(1.5 * (attempt + 1))
        raise DataUnavailable(f"Could not fetch {url}: {last_err or 'rate limited'}")

    def get_json(self, url: str, **kw):
        return json.loads(self.get(url, **kw))
