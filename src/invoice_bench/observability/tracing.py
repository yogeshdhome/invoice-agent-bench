"""Minimal OTel tracing with GenAI-convention span names (attribute names isolated here; conventions are
at Development status, so keep them in one place)."""
from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.trace import Status, StatusCode

A_OP, A_TOOL, A_IN, A_OUT, A_CACHED, A_AGENT = ("gen_ai.operation.name", "gen_ai.tool.name", "gen_ai.usage.input_tokens",
                                                "gen_ai.usage.output_tokens", "gen_ai.usage.cache_read.input_tokens",
                                                "gen_ai.agent.name")


class JsonlExporter(SpanExporter):
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def export(self, spans):
        with self.path.open("a") as f:
            for s in spans:
                f.write(json.dumps({"name": s.name, "trace_id": f"{s.context.trace_id:032x}", "span_id": f"{s.context.span_id:016x}",
                                    "parent": f"{s.parent.span_id:016x}" if s.parent else None,
                                    "start_ns": s.start_time, "end_ns": s.end_time, "status": s.status.status_code.name,
                                    "attrs": dict(s.attributes)}) + "\n")
        return SpanExportResult.SUCCESS


class RunTracer:
    def __init__(self, path: Path | None):
        self.provider = TracerProvider()
        if path:
            self.provider.add_span_processor(SimpleSpanProcessor(JsonlExporter(path)))
        self.t = self.provider.get_tracer("invoice_bench")

    @contextmanager
    def agent_run(self, agent_name: str, run_id: str):
        with self.t.start_as_current_span("invoke_agent", attributes={A_OP: "invoke_agent", A_AGENT: agent_name,
                                                                       "run.id": run_id}) as s:
            yield s

    @contextmanager
    def tool(self, name: str):
        with self.t.start_as_current_span("execute_tool", attributes={A_OP: "execute_tool", A_TOOL: name}) as s:
            yield s

    def mark_error(self, span, err: str):
        span.set_status(Status(StatusCode.ERROR, err))
        span.set_attribute("error.type", err)

    def chat_span(self, it: int, ot: int, cached: int):
        with self.t.start_as_current_span("chat", attributes={A_OP: "chat", A_IN: it, A_OUT: ot, A_CACHED: cached}):
            pass
