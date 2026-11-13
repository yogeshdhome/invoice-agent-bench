"""SQLite-backed LangChain LLM cache for zero-cost replay. One cache file per trial index, so repeated
trials are NOT collapsed into one response (that would fake determinism)."""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from langchain_core.caches import BaseCache
from langchain_core.load import dumps, loads


class SQLiteLLMCache(BaseCache):
    def __init__(self, path: str | Path, read_only: bool = False):
        self.path, self.read_only = str(path), read_only
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as c:
            c.execute("CREATE TABLE IF NOT EXISTS cache(k TEXT PRIMARY KEY, v TEXT NOT NULL)")

    @staticmethod
    def _k(prompt: str, llm_string: str) -> str:
        return hashlib.sha256((llm_string + "\x00" + prompt).encode()).hexdigest()

    def lookup(self, prompt, llm_string):
        with sqlite3.connect(self.path) as c:
            r = c.execute("SELECT v FROM cache WHERE k=?", [self._k(prompt, llm_string)]).fetchone()
        return loads(r[0]) if r else None

    def update(self, prompt, llm_string, return_val):
        if self.read_only:
            return
        with sqlite3.connect(self.path) as c:
            c.execute("INSERT OR REPLACE INTO cache VALUES (?,?)", [self._k(prompt, llm_string), dumps(return_val)])

    def clear(self, **kwargs):
        with sqlite3.connect(self.path) as c:
            c.execute("DELETE FROM cache")
