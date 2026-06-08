"""Prometheus metrics shared helpers."""

from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["service", "method", "endpoint", "status"],
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["service", "method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

ACCOUNT_SERVICE_CALLS = Counter(
    "account_service_calls_total",
    "Calls from gateway to account service",
    ["operation", "status"],
)

CIRCUIT_BREAKER_STATE = Counter(
    "circuit_breaker_trips_total",
    "Circuit breaker open events",
    ["service"],
)

QUEUED_EVENTS = Counter(
    "queued_events_total",
    "Events queued when account service unavailable",
    ["status"],
)


def metrics_response():
    return generate_latest(), CONTENT_TYPE_LATEST
