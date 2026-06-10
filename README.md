# Event Ledger

A take-home project turned into a **production-style distributed systems demo**: two FastAPI microservices that ingest financial events, tolerate duplicates and out-of-order delivery, and stay observable and resilient when dependencies fail.

The brief asked for a working ledger with tracing and one resiliency pattern. This implementation goes further — private service boundaries, full observability stack, contract testing, async recovery, and AWS deployment — while keeping the codebase small and readable.

## Live demo (AWS)

Deployed on ECS Fargate. Account Service is VPC-private; only the Gateway and Jaeger UI are public.

| Resource | URL |
|---|---|
| **Gateway API** | http://event-ledger-alb-1832743372.us-east-1.elb.amazonaws.com |
| **API documentation** | http://event-ledger-alb-1832743372.us-east-1.elb.amazonaws.com/docs |
| **Health check** | http://event-ledger-alb-1832743372.us-east-1.elb.amazonaws.com/health |
| **Jaeger UI** | http://event-ledger-alb-1832743372.us-east-1.elb.amazonaws.com:8080 |

Tracing runs in the VPC: services export OTLP to `otel-collector.event-ledger.local`, which forwards to Jaeger. Submit an event via the Gateway, then open Jaeger and select `event-gateway` and `account-service` to see the distributed trace.

```bash
curl -X POST http://event-ledger-alb-1832743372.us-east-1.elb.amazonaws.com/events \
  -H "Content-Type: application/json" \
  -d '{"eventId":"evt-demo-001","accountId":"acct-demo","type":"CREDIT","amount":"150.00","currency":"USD","eventTimestamp":"2026-06-09T18:00:00Z"}'
```

## Beyond the requirements

| Area | What was added |
|---|---|
| **Money safety** | `Decimal` end-to-end, `NUMERIC(20,4)` storage, overflow guards — no floats near balances |
| **Resilience** | Circuit breaker *and* timeout/retry with exponential backoff + jitter; background queue replays failed writes |
| **Observability** | OpenTelemetry → Collector → Jaeger, Prometheus metrics, structured JSON logs with correlated trace IDs |
| **API contracts** | Shared Pydantic models, enriched OpenAPI docs, JSON Schema checks, and Pact consumer/provider tests |
| **Operations** | Docker Compose (prod-like network isolation), rate limiting, health checks, 43 automated tests with coverage |
| **Cloud** | ECS Fargate on AWS — public Gateway via ALB, Account Service in private subnets with security-group isolation, GitHub Actions OIDC deploy |

**Architectural choices worth noting:**

- **Gateway owns the event log; Account owns balances** — separate SQLite databases, no shared state, clear bounded context.
- **Graceful degradation** — reads from Gateway local storage keep working when Account is down; writes are queued for replay.
- **Trace propagation** — W3C `traceparent` plus `X-Trace-Id` so a single `POST /events` appears as one distributed trace in Jaeger.

## Architecture

```
Client ──→ Event Gateway (:8000, public)
              │ REST + trace headers
              ▼
         Account Service (:8001, internal only)
```

Interactive API docs: `http://localhost:8000/docs` after startup.

Deeper design: [Cloud Architecture](docs/cloud-architecture.md) · [CI/CD](docs/ci-cd.md)

## Quick start

**Prerequisites:** Python 3.11+, [uv](https://docs.astral.sh/uv/getting-started/installation/), Docker Compose.

```bash
uv venv && uv pip install -e ".[dev]"
docker compose up --build
```

| What | URL |
|---|---|
| Gateway | http://localhost:8000 |
| Swagger UI | http://localhost:8000/docs |
| Jaeger | http://localhost:16686 |
| Metrics | http://localhost:8000/metrics |

Submit an event, then open Jaeger and select `event-gateway` and `account-service` to see the full trace:

```bash
curl -X POST http://localhost:8000/events \
  -H "Content-Type: application/json" \
  -d '{"eventId":"evt-001","accountId":"acct-123","type":"CREDIT","amount":"150.00","currency":"USD","eventTimestamp":"2026-05-15T14:02:11Z"}'
```

Run tests (unit, integration, contract/Pact):

```bash
uv run pytest
open htmlcov/index.html   # coverage report
```

## Security posture (demo scope)

Appropriate for a portfolio demo, not production as-is:

- **No authentication** on public endpoints — would add API gateway auth or mTLS in production.
- **HTTP only** locally and on AWS ALB — HTTPS via ACM is documented in hardening notes.
- **Account Service is network-isolated** — private subnet, security group allows only Gateway ingress.
- **Input validation** via Pydantic; SQLAlchemy ORM (parameterized queries); rate limiting on `POST /events`.
- **Secrets** — no credentials in repo; AWS deploy uses GitHub OIDC, not long-lived keys.

## AWS deployment

Infrastructure is defined in Terraform and deployed via GitHub Actions on push to `main`. See [infrastructure/aws/README.md](infrastructure/aws/README.md) for manual deploy/teardown and [docs/ci-cd.md](docs/ci-cd.md) for the pipeline.

**Cost control:** set GitHub repo variable `DESTROY_AFTER` to a date (`YYYY-MM-DD`, e.g. one week after deploy). A scheduled workflow runs `terraform destroy` on or after that day. Resources bill **per hour** while up (NAT and ALB are the largest fixed costs).

## Project layout

```
ledger_common/     Shared schemas, tracing, metrics, OpenAPI helpers
services/gateway/  Public API, idempotency, resiliency, event store
services/account/  Balances and transaction application
tests/             Unit, integration, contract (JSON Schema + Pact)
infrastructure/aws Terraform + ECS Fargate
```
