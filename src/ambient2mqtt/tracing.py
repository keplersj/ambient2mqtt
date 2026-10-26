"""Optional OpenTelemetry tracing.

Off unless an OTLP endpoint is configured with the standard environment variables
(OTEL_EXPORTER_OTLP_ENDPOINT or OTEL_EXPORTER_OTLP_TRACES_ENDPOINT) and the `otel` extra
is installed (it is in the container image). Everything else follows the OTel spec's env
vars: OTEL_SERVICE_NAME, OTEL_RESOURCE_ATTRIBUTES, OTEL_TRACES_SAMPLER, OTEL_SDK_DISABLED...

When disabled, `span()` is a no-op and `exemplar()` / `current_ids()` return None, so
callers never need to check.
"""

from __future__ import annotations

import contextlib
import logging
import os
from collections.abc import Iterator
from typing import Any

log = logging.getLogger(__name__)

_tracer: Any = None
_provider: Any = None


def enabled() -> bool:
    return _tracer is not None


def setup(version: str) -> bool:
    """Configure the tracer provider and httpx instrumentation; returns True if enabled."""
    global _tracer, _provider
    if not (
        os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        or os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
    ):
        return False
    if os.environ.get("OTEL_SDK_DISABLED", "").strip().lower() == "true":
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        log.warning(
            "OTEL_EXPORTER_OTLP_ENDPOINT is set but OpenTelemetry is not installed; "
            "install ambient2mqtt[otel] to enable tracing"
        )
        return False

    attrs: dict[str, str] = {"service.version": version}
    if not os.environ.get("OTEL_SERVICE_NAME") and "service.name=" not in os.environ.get(
        "OTEL_RESOURCE_ATTRIBUTES", ""
    ):
        attrs["service.name"] = "ambient2mqtt"
    _provider = TracerProvider(resource=Resource.create(attrs))
    _provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(_provider)
    # Must run before AmbientClient builds its httpx.AsyncClient.
    HTTPXClientInstrumentor().instrument()
    _tracer = trace.get_tracer("ambient2mqtt", version)
    log.info("OpenTelemetry tracing enabled (OTLP/HTTP)")
    return True


def shutdown() -> None:
    """Flush pending spans."""
    if _provider is not None:
        _provider.shutdown()


@contextlib.contextmanager
def span(name: str, *, kind: str = "internal", **attributes: Any) -> Iterator[Any]:
    """Start a span (no-op when tracing is off). `kind`: internal / consumer / client."""
    if _tracer is None:
        yield None
        return
    from opentelemetry.trace import SpanKind

    span_kind = {"consumer": SpanKind.CONSUMER, "client": SpanKind.CLIENT}.get(
        kind, SpanKind.INTERNAL
    )
    attrs = {k: v for k, v in attributes.items() if v is not None}
    with _tracer.start_as_current_span(name, kind=span_kind, attributes=attrs) as s:
        yield s


def set_attributes(**attributes: Any) -> None:
    if _tracer is None:
        return
    from opentelemetry import trace

    trace.get_current_span().set_attributes({k: v for k, v in attributes.items() if v is not None})


def record_error(exc: BaseException) -> None:
    """Mark the active span failed (for exceptions caught before they leave the span)."""
    if _tracer is None:
        return
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode

    current = trace.get_current_span()
    current.record_exception(exc)
    current.set_status(Status(StatusCode.ERROR, str(exc)))


def add_event(name: str, **attributes: Any) -> None:
    if _tracer is None:
        return
    from opentelemetry import trace

    trace.get_current_span().add_event(name, attributes)


def current_ids() -> tuple[str, str] | None:
    """(trace_id, span_id) as hex for the active sampled span, else None."""
    if _tracer is None:
        return None
    from opentelemetry import trace

    ctx = trace.get_current_span().get_span_context()
    if not ctx.is_valid or not ctx.trace_flags.sampled:
        return None
    return format(ctx.trace_id, "032x"), format(ctx.span_id, "016x")


def exemplar() -> dict[str, str] | None:
    """Prometheus exemplar labels linking an observation to the active trace."""
    ids = current_ids()
    return {"trace_id": ids[0], "span_id": ids[1]} if ids else None
