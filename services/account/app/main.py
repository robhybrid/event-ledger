from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from ledger_common.logging import configure_logging, get_logger
from ledger_common.metrics import REQUEST_COUNT, REQUEST_LATENCY, metrics_response
from ledger_common.tracing import (
    TraceIdMiddleware,
    flush_tracing,
    instrument_fastapi,
    setup_tracing,
    shutdown_tracing,
)
from services.account.app.config import settings
from services.account.app.database import check_db, init_db
from ledger_common.openapi import OPENAPI_TAGS, TAG_HEALTH, TAG_METRICS, install_contract_openapi
from services.account.app.routes import router

configure_logging(settings.service_name, settings.log_level)
logger = get_logger(__name__)

setup_tracing(settings.service_name, settings.otlp_endpoint)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("account_service_started", port=settings.port)
    yield
    flush_tracing()
    shutdown_tracing()
    logger.info("account_service_stopped")


app = FastAPI(
    title="Account Service",
    description=(
        "Internal service for account balances and transactions.\n\n"
        "**Contracts:** `ApplyTransactionRequest`, `TransactionRecord`, "
        "`BalanceResponse`, and `AccountDetailResponse` are defined in "
        "`ledger_common.schemas`. The Event Gateway is the Pact consumer; "
        "verified contracts are stored in `tests/pacts/`."
    ),
    version="1.0.0",
    openapi_tags=OPENAPI_TAGS,
    lifespan=lifespan,
)
instrument_fastapi(app, settings.service_name)
app.add_middleware(TraceIdMiddleware)
app.include_router(router)
install_contract_openapi(app)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = perf_counter()
    response = await call_next(request)
    duration = perf_counter() - start
    endpoint = request.url.path
    REQUEST_LATENCY.labels(
        service=settings.service_name,
        method=request.method,
        endpoint=endpoint,
    ).observe(duration)
    REQUEST_COUNT.labels(
        service=settings.service_name,
        method=request.method,
        endpoint=endpoint,
        status=str(response.status_code),
    ).inc()
    return response


@app.get("/health", tags=[TAG_HEALTH], summary="Account Service health check")
async def health():
    db_ok = await check_db()
    status_code = 200 if db_ok else 503
    body = {
        "status": "healthy" if db_ok else "unhealthy",
        "service": settings.service_name,
        "database": "connected" if db_ok else "disconnected",
    }
    return JSONResponse(content=body, status_code=status_code)


@app.get("/metrics", tags=[TAG_METRICS], summary="Prometheus metrics")
async def metrics():
    content, content_type = metrics_response()
    return Response(content=content, media_type=content_type)
