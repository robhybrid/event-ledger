from opentelemetry import trace
from opentelemetry.baggage.propagation import W3CBaggagePropagator
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from ledger_common.tracing import TRACE_ID_HEADER, trace_headers


def test_trace_headers_include_w3c_traceparent():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    set_global_textmap(
        CompositePropagator([TraceContextTextMapPropagator(), W3CBaggagePropagator()])
    )

    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("parent-span"):
        headers = trace_headers()

    assert "traceparent" in headers
    assert headers["traceparent"].startswith("00-")
    assert TRACE_ID_HEADER in headers
