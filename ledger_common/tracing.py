"""OpenTelemetry tracing setup and trace ID propagation."""

import os
import sys
import uuid
from contextvars import ContextVar

from fastapi import Request
from opentelemetry import trace
from opentelemetry.baggage.propagation import W3CBaggagePropagator
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.propagate import inject, set_global_textmap
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from starlette.middleware.base import BaseHTTPMiddleware

TRACE_ID_HEADER = "X-Trace-Id"
trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)


def _running_under_pytest() -> bool:
    return "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ


def shutdown_tracing() -> None:
    """Flush and stop the active tracer provider (safe to call when none is set)."""
    provider = trace.get_tracer_provider()
    if isinstance(provider, TracerProvider):
        provider.shutdown()


def setup_tracing(service_name: str, otlp_endpoint: str | None = None) -> None:
    """Configure the global tracer provider and outbound HTTP instrumentation."""
    shutdown_tracing()

    set_global_textmap(
        CompositePropagator([TraceContextTextMapPropagator(), W3CBaggagePropagator()])
    )

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    if otlp_endpoint:
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        provider.add_span_processor(
            BatchSpanProcessor(
                exporter,
                schedule_delay_millis=1000,
                max_export_batch_size=256,
            )
        )
    elif not _running_under_pytest():
        # Console export uses a background thread; skip during pytest to avoid
        # "I/O operation on closed file" when the batch processor flushes at exit.
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    HTTPXClientInstrumentor().instrument()


def flush_tracing(timeout_millis: int = 5000) -> bool:
    """Flush pending spans to the configured exporter."""
    provider = trace.get_tracer_provider()
    if isinstance(provider, TracerProvider):
        return provider.force_flush(timeout_millis)
    return True


def instrument_fastapi(app, _service_name: str) -> None:
    provider = trace.get_tracer_provider()
    kwargs: dict = {
        "excluded_urls": "/health,/metrics",
        # Keep a single server span per request so outbound httpx calls inherit
        # the same trace ID instead of splitting into separate traces.
        "exclude_spans": ["receive", "send"],
    }
    if isinstance(provider, TracerProvider):
        kwargs["tracer_provider"] = provider
    FastAPIInstrumentor.instrument_app(app, **kwargs)


def get_tracer(name: str):
    return trace.get_tracer(name, schema_url="https://opentelemetry.io/schemas/1.11.0")


class TraceIdMiddleware(BaseHTTPMiddleware):
    """Expose the active OpenTelemetry trace ID for logs and response headers."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        trace_id = _resolve_trace_id(request)
        trace_id_var.set(trace_id)

        structlog_bind = _get_structlog_bind()
        if structlog_bind:
            structlog_bind(trace_id=trace_id)

        response.headers[TRACE_ID_HEADER] = trace_id
        return response


def _resolve_trace_id(request: Request) -> str:
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        return format(span.get_span_context().trace_id, "032x")
    return request.headers.get(TRACE_ID_HEADER) or str(uuid.uuid4())


def _get_structlog_bind():
    try:
        import structlog

        return structlog.contextvars.bind_contextvars
    except ImportError:
        return None


def get_trace_id() -> str | None:
    tid = trace_id_var.get()
    if tid:
        return tid

    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        return format(span.get_span_context().trace_id, "032x")
    return None


def trace_headers() -> dict[str, str]:
    """Build outbound headers with W3C trace context and X-Trace-Id for log correlation."""
    headers: dict[str, str] = {}
    inject(headers)
    tid = get_trace_id()
    if tid:
        headers[TRACE_ID_HEADER] = tid
    return headers
