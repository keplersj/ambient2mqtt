"""Tests for optional OpenTelemetry tracing (in-memory exporter; nothing leaves the process)."""

import json
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("opentelemetry.sdk", reason="needs the otel extra (uv sync --all-extras)")

from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter  # noqa: E402
from prometheus_client import REGISTRY  # noqa: E402
from prometheus_client.openmetrics.exposition import generate_latest  # noqa: E402

from ambient2mqtt import tracing  # noqa: E402
from ambient2mqtt.bridge import Bridge  # noqa: E402
from ambient2mqtt.client import AmbientError  # noqa: E402
from ambient2mqtt.config import Settings  # noqa: E402
from ambient2mqtt.logs import JsonFormatter  # noqa: E402


@pytest.fixture
def spans(monkeypatch) -> InMemorySpanExporter:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(tracing, "_tracer", provider.get_tracer("test"))
    return exporter


def light(state: str) -> dict:
    return {"deviceId": "dev-light", "traits": {"lightReadV1": {"status": {"lightState": state}}}}


@pytest.fixture
def bridge(monkeypatch) -> Bridge:
    monkeypatch.setattr(Bridge, "_SETTLE_DELAYS", (0,))
    b = Bridge(MagicMock(), Settings(username="u", password="p"))
    b.mqtt = MagicMock()
    b._devices = {"dev-light": light("LIGHT_STATE_OFF")}
    b.client.set_light = AsyncMock()
    b.client.get_world = AsyncMock(return_value={"devices": [light("LIGHT_STATE_ON")]})
    return b


def test_disabled_without_endpoint(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    assert tracing.setup("0") is False
    with tracing.span("x") as s:
        assert s is None
    assert tracing.exemplar() is None
    assert tracing.current_ids() is None


def test_sdk_disabled_wins(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4318")
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    assert tracing.setup("0") is False


async def test_command_trace_nests_settle_and_sync(spans, bridge):
    await bridge._handle_command("ambient2mqtt/dev-light/set", "ON")
    by_name = {s.name: s for s in spans.get_finished_spans()}
    cmd, settle, sync = (
        by_name["ambient2mqtt.command"],
        by_name["ambient2mqtt.settle"],
        by_name["ambient2mqtt.sync"],
    )
    assert cmd.attributes["ambient2mqtt.command.kind"] == "light"
    assert cmd.attributes["messaging.destination.name"] == "ambient2mqtt/dev-light/set"
    assert settle.parent.span_id == cmd.context.span_id
    assert sync.parent.span_id == settle.context.span_id
    assert settle.attributes["ambient2mqtt.state.changed"] is True
    assert [e.name for e in settle.events] == ["state.changed"]


async def test_failed_command_marks_span_error(spans, bridge):
    bridge.client.set_light = AsyncMock(side_effect=AmbientError("nope"))
    await bridge._handle_command("ambient2mqtt/dev-light/set", "ON")
    (cmd,) = spans.get_finished_spans()
    assert not cmd.status.is_ok
    assert cmd.events[0].name == "exception"


async def test_command_duration_carries_trace_exemplar(spans, bridge):
    await bridge._handle_command("ambient2mqtt/dev-light/set", "ON")
    cmd = next(s for s in spans.get_finished_spans() if s.name == "ambient2mqtt.command")
    trace_id = format(cmd.context.trace_id, "032x")
    exposition = generate_latest(REGISTRY).decode()
    assert f'trace_id="{trace_id}"' in exposition


def test_json_logs_include_trace_ids(spans):
    record = logging.LogRecord("t", logging.INFO, "", 0, "hello", (), None)
    with tracing.span("op") as s:
        out = json.loads(JsonFormatter().format(record))
    assert out["trace_id"] == format(s.get_span_context().trace_id, "032x")
    assert out["span_id"] == format(s.get_span_context().span_id, "016x")
