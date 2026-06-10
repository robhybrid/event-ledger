# Event Ledger

A production-style proof-of-concept for processing financial transaction events across two independent microservices. Built with Python, FastAPI, and SQLite to demonstrate distributed systems engineering: idempotency, out-of-order tolerance, observability, resiliency, and graceful degradation.

## Documentation

| Document | Description |
|---|---|
| [Cloud Architecture](docs/cloud-architecture.md) | AWS VPC topology, security groups, request flow |
| [CI/CD Guide](docs/ci-cd.md) | GitHub Actions workflows, OIDC deployment, rollback |

## Architecture

```
Browser / Client ──→ Event Gateway API (public, :8000)
                           │ REST (sync)
                           ▼
                     Account Service (internal, :8001)
```

| Service | Responsibility |
|---|---|
| **Event Gateway** | Public API, input validation, idempotency, event storage, calls Account Service |
| **Account Service** | Account balances, transaction application, balance queries |

Each service runs as an independent process with its own SQLite database. They do not share state.

### Financial data handling

- **No floating-point amounts** — all monetary values use Python `Decimal`, stored as `NUMERIC(20,4)` in SQLite
- **Overflow protection** — balances and amounts are validated against `MAX_AMOUNT` before persistence
- **Idempotency** — duplicate `eventId` submissions return the original event (HTTP 200)
- **Out-of-order tolerance** — events are listed by `eventTimestamp`; balances are computed as sum(CREDIT) − sum(DEBIT)

### Resiliency

The Gateway implements two complementary patterns on calls to the Account Service:

1. **Circuit breaker** — after 5 consecutive failures, the breaker opens for 30 seconds and returns HTTP 503 immediately
2. **Timeout + retry with exponential backoff and jitter** — transient network errors are retried up to 3 times via `tenacity`

When the Account Service is unavailable, `POST /events` returns HTTP 503 but stores the event locally and enqueues it for background processing (async fallback). `GET /events` endpoints continue to work from the Gateway's local database.

### Observability

- **Structured JSON logging** with `trace_id`, timestamp, level, and service name
- **Distributed tracing** via OpenTelemetry with W3C `traceparent` propagation and `X-Trace-Id` for log correlation
- **Prometheus metrics** at `GET /metrics` on both services
- **Jaeger UI** at `http://localhost:16686` when running via Docker Compose

## Prerequisites

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/getting-started/installation/)** — fast Python package and virtual environment manager ([installation guide](https://docs.astral.sh/uv/getting-started/installation/))
- **[Docker](https://docs.docker.com/get-started/get-docker/)** & **Docker Compose** — required to run the full stack with observability ([Docker Desktop](https://www.docker.com/products/docker-desktop/) is the easiest way to install on macOS and Windows)

## Local development

```bash
# Clone and enter the project
cd event-ledger

# Create virtual environment and install dependencies
uv venv
uv pip install -e ".[dev]"

# Activate the virtual environment (optional — uv run works without this)
source .venv/bin/activate   # macOS/Linux
```

### Start services manually

Terminal 1 — Account Service:

```bash
uv run uvicorn services.account.app.main:app --host 0.0.0.0 --port 8001 --reload
```

Terminal 2 — Gateway:

```bash
GATEWAY_ACCOUNT_SERVICE_URL=http://localhost:8001 \
  uv run uvicorn services.gateway.app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Start with Docker Compose

The default compose file mirrors production topology: **only the Gateway and Jaeger are exposed** to your host. Account Service is internal to the Docker network.

```bash
docker compose up --build
```

For local debugging with Account Service and the OTLP collector exposed on the host:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

You can also start the stack from the **Run and Debug** panel — **Docker Compose: Up (Dev)** includes the dev overrides.

| Endpoint | URL | Default compose | Dev override |
|---|---|---|---|
| Gateway API | http://localhost:8000 | Yes | Yes |
| API Documentation | http://localhost:8000/docs | Yes | Yes |
| Account Service | http://localhost:8001 | No (internal only) | Yes |
| Jaeger UI | http://localhost:16686 | Yes | Yes |
| Gateway metrics | http://localhost:8000/metrics | Yes | Yes |
| Account metrics | http://localhost:8001/metrics | No | Yes |

**Jaeger:** open http://localhost:16686 in your browser (not the Docker terminal logs). Select both `event-gateway` and `account-service` from the Service dropdown. Submit a `POST /events` request to generate a distributed trace spanning both services.

### Example request

```bash
curl -X POST http://localhost:8000/events \
  -H "Content-Type: application/json" \
  -d '{
    "eventId": "evt-001",
    "accountId": "acct-123",
    "type": "CREDIT",
    "amount": "150.00",
    "currency": "USD",
    "eventTimestamp": "2026-05-15T14:02:11Z"
  }'
```

## Running tests

```bash
uv run pytest
open htmlcov/index.html   # macOS — view the report in your browser
```

Every test run generates an **HTML coverage report** at `htmlcov/index.html` (configured in `pyproject.toml`).

On GitHub Actions, download the `html-coverage-report` artifact from any CI run.

Test coverage includes:

- Core functionality (idempotency, out-of-order, balance, validation)
- Circuit breaker and retry behavior
- Trace ID propagation
- Full Gateway → Account Service integration flow
- JSON Schema and **Pact** consumer/provider contract tests (`tests/contract/`, `tests/pacts/`)
- OpenAPI/Swagger docs include shared contract schemas (`ledger_common.schemas`)

## Bonus features

Stretch goals from the project requirements that are implemented:

| Feature | Status |
|---|---|
| OpenTelemetry Collector + Jaeger trace visualization | Implemented (`docker-compose.yml`, Jaeger UI at `:16686`) |
| Prometheus metrics endpoint | Implemented (`GET /metrics` on both services) |
| Retry with exponential backoff + jitter | Implemented (`tenacity` in Gateway Account Service client) |
| Rate limiting on the Gateway | Implemented (`slowapi`, default `100/minute`) |
| Contract tests (JSON Schema + Pact) | Implemented (`tests/contract/`, `tests/pacts/`) |
| Async fallback: local queue when Account Service is down | Implemented (`queue_worker`, `GATEWAY_QUEUE_PROCESSING_ENABLED`) |
| AWS deployment (ECS Fargate) | Implemented (`infrastructure/aws/`) |

## AWS deployment

Infrastructure for **ECS Fargate** is defined in Terraform and deployed via GitHub Actions. The stack is not kept running by default (to avoid idle AWS cost). See [docs/ci-cd.md](docs/ci-cd.md) for the pipeline and [infrastructure/aws/README.md](infrastructure/aws/README.md) for deploy and teardown steps.

## Project structure

```
├── ledger_common/          # Shared schemas, Decimal handling, tracing, metrics
├── services/
│   ├── gateway/            # Public-facing Event Gateway API
│   └── account/            # Internal Account Service
├── tests/
│   ├── unit/
│   ├── integration/
│   └── contract/
├── docs/                   # Cloud architecture and CI/CD guides
├── infrastructure/aws/     # Terraform for ECS Fargate
├── .github/workflows/      # CI (pytest) and CD (AWS deploy)
├── docker-compose.yml
├── Dockerfile
└── pyproject.toml
```

## API reference

### Gateway (public)

| Method | Endpoint | Description |
|---|---|---|
| POST | `/events` | Submit a transaction event |
| GET | `/events/{id}` | Retrieve event by ID |
| GET | `/events?account={id}` | List events for account (chronological) |
| GET | `/accounts/{id}/balance` | Proxy balance query to Account Service |
| GET | `/health` | Health check |
| GET | `/metrics` | Prometheus metrics |

### Account Service (internal)

| Method | Endpoint | Description |
|---|---|---|
| POST | `/accounts/{id}/transactions` | Apply a transaction |
| GET | `/accounts/{id}/balance` | Get current balance |
| GET | `/accounts/{id}` | Account details and transactions |
| GET | `/health` | Health check |
| GET | `/metrics` | Prometheus metrics |
