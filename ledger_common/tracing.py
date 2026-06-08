"""OpenTelemetry tracing setup and trace ID propagation."""

import uuid
from contextvars import ContextVar

from fastapi import Request
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from starlette.middleware.base import BaseHTTPMiddleware

TRACE_ID_HEADER = "X-Trace-Id"
trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)


def setup_tracing(service_name: str, otlp_endpoint: str | None = None) -> None:
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    if otlp_endpoint:
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
    else:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    HTTPXClientInstrumentor().instrument()


def instrument_fastapi(app, service_name: str) -> None:
    FastAPIInstrumentor.instrument_app(app, excluded_urls="/health,/metrics")


class TraceIdMiddleware(BaseHTTPMiddleware):
    """Ensure every request has a trace ID in context and response headers."""

    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get(TRACE_ID_HEADER) or str(uuid.uuid4())
        trace_id_var.set(trace_id)

        span = trace.get_current_span()
        if span and span.get_span_context().is_valid:
            trace_id = format(span.get_span_context().trace_id, "032x")
            trace_id_var.set(trace_id)

        structlog_bind = _get_structlog_bind()
        if structlog_bind:
            structlog_bind(trace_id=trace_id)

        response = await call_next(request)
        response.headers[TRACE_ID_HEADER] = trace_id
        return response


def _get_structlog_bind():
    try:
        import structlog

        return structlog.contextvars.bind_contextvars
    except ImportError:
        return None


def get_trace_id() -> str | None:
    return trace_id_var.get()


def trace_headers() -> dict[str, str]:
    tid = get_trace_id()
    if tid:
        return {TRACE_ID_HEADER: tid}
    return {}
