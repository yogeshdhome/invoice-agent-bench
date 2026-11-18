"""Append-only audit log (business record, separate from traces). Stored in the run directory, not the world DB."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ..domain.canonical import canonical_json


class AuditLog:
    def __init__(self, path: Path | str | None):
        self.path = str(path) if path else ":memory:"
        self.c = sqlite3.connect(self.path, check_same_thread=False)
        self.c.execute("CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, run_id TEXT, "
                       "principal TEXT, event TEXT, rule_id TEXT, payload TEXT)")
        self.c.execute("CREATE TRIGGER IF NOT EXISTS no_update BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT,'append-only'); END")
        self.c.execute("CREATE TRIGGER IF NOT EXISTS no_delete BEFORE DELETE ON audit BEGIN SELECT RAISE(ABORT,'append-only'); END")

    def log(self, run_id: str, principal: str, event: str, rule_id: str | None = None, **payload) -> None:
        self.c.execute("INSERT INTO audit(ts, run_id, principal, event, rule_id, payload) VALUES (?,?,?,?,?,?)",
                       [datetime.now(timezone.utc).isoformat(timespec="milliseconds"), run_id, principal, event, rule_id,
                        canonical_json(payload)])
        self.c.commit()

    def events(self, run_id: str | None = None) -> list[dict]:
        q = "SELECT seq, event, rule_id, payload FROM audit" + (" WHERE run_id=?" if run_id else "") + " ORDER BY seq"
        return [{"seq": s, "event": e, "rule_id": r, **json.loads(p)} for s, e, r, p in self.c.execute(q, [run_id] if run_id else [])]
