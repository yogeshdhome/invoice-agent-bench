import asyncio
import sqlite3
from pathlib import Path

import httpx
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from invoice_bench.agents.hardened.graph import HardenedDeps, build_hardened
from invoice_bench.bench.run import RunSettings, load_scenarios, run_one
from invoice_bench.llm.fake import ScriptedChatModel
from invoice_bench.llm.usage import BudgetCallback
from invoice_bench.observability.audit import AuditLog
from invoice_bench.security.auth import Principal, issue_token
from invoice_bench.security.policy import PolicyEngine
from invoice_bench.services.app import create_app
from invoice_bench.services.db import connect
from invoice_bench.services.faults import FaultController
from invoice_bench.services.repository import users_from_db
from invoice_bench.tools.client import ServiceClient
from invoice_bench.tools.resilient import ResilientClient, RetryPolicy


def scenarios(dataset: Path) -> dict:
    return {s.scenario_id: s for s in load_scenarios(dataset, "all")}


def run(sc, arm, script, dataset, tmp, **kw):
    st = RunSettings(dataset, tmp, latency=False, fault_delay_s=0.3, client_timeout_s=0.1, backoff_initial_s=0.01, **kw)
    return asyncio.run(run_one(sc, arm, 0, ScriptedChatModel(script=list(script)), st))


class Rig:
    """Direct access to a hardened graph over a fresh world copy (for crash/resume and approval-forgery tests)."""

    def __init__(self, world_db: Path, persona: dict, script, crash_hook=None, checkpointer=None):
        self.db = world_db
        self.app = create_app(str(world_db), faults=FaultController(), today="2026-11-02")
        self.persona = Principal(user_id=persona["user_id"], tenant_id=persona["tenant_id"], bu_ids=tuple(persona["bu_ids"]),
                                 roles=tuple(persona["roles"]))
        self.inner = ServiceClient(httpx.ASGITransport(app=self.app), issue_token(self.persona))
        self.model = ScriptedChatModel(script=list(script))
        conn = connect(world_db)
        self.policy = PolicyEngine.from_yaml("config/policies.yaml")
        self.audit = AuditLog(None)
        self.deps = HardenedDeps(self.model, ResilientClient(self.inner, RetryPolicy(backoff_initial_s=0.01)), self.policy,
                                 users_from_db(conn), self.audit, crash_hook=crash_hook)
        conn.close()
        self.cp = checkpointer or InMemorySaver()
        self.graph = build_hardened(self.deps, self.cp)
        self.config = {"configurable": {"thread_id": "t1", "principal": self.persona.model_dump(mode="json"), "bench_run_id": "r1"},
                       "callbacks": [BudgetCallback(5, 24000)]}

    def invoke(self, payload):
        return asyncio.run(self.graph.ainvoke(payload, self.config, durability="sync"))

    def resume(self, value):
        return self.invoke(Command(resume=value))

    def restart(self, crash_hook=None):
        """Simulate a process restart: new graph object, same checkpointer and same services."""
        self.deps.crash_hook = crash_hook
        self.graph = build_hardened(self.deps, self.cp)

    def q(self, sql, *a):
        return sqlite3.connect(self.db).execute(sql, a).fetchall()
