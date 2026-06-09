"""OpenTelemetry tracing setup and trace ID propagation."""

import uuid
from contextvars import ContextVar

from fastapi import Request
from opentelemetry import context, trace
from opentelemetry.baggage.propagation import W3CBaggagePropagator
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.propagate import extract, inject, set_global_textmap
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from starlette.middleware.base import BaseHTTPMiddleware

TRACE_ID_HEADER = "X-Trace-Id"
trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)


def setup_tracing(service_name: str, otlp_endpoint: str | None = None) -> None:
    set_global_textmap(
        CompositePropagator([TraceContextTextMapPropagator(), W3CBaggagePropagator()])
    )

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
    """Extract W3C trace context and ensure trace ID is available for logs and headers."""

    async def dispatch(self, request: Request, call_next):
        ctx = extract(dict(request.headers))
        token = context.attach(ctx)

        try:
            span = trace.get_current_span()
            if span and span.get_span_context().is_valid:
                trace_id = format(span.get_span_context().trace_id, "032x")
            else:
                trace_id = request.headers.get(TRACE_ID_HEADER) or str(uuid.uuid4())

            trace_id_var.set(trace_id)

            structlog_bind = _get_structlog_bind()
            if structlog_bind:
                structlog_bind(trace_id=trace_id)

            response = await call_next(request)
            response.headers[TRACE_ID_HEADER] = trace_id
            return response
        finally:
            context.detach(token)


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
