import asyncio
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from ledger_common.logging import configure_logging, get_logger
from ledger_common.metrics import REQUEST_COUNT, REQUEST_LATENCY, metrics_response
from ledger_common.tracing import TraceIdMiddleware, instrument_fastapi, setup_tracing
from services.gateway.app.config import settings
from services.gateway.app.limiter import limiter
from services.gateway.app.database import check_db, init_db
from services.gateway.app.queue_worker import queue_worker_loop
from services.gateway.app.routes import router

configure_logging(settings.service_name, settings.log_level)
logger = get_logger(__name__)

_stop_event: asyncio.Event | None = None
_worker_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _stop_event, _worker_task
    setup_tracing(settings.service_name, settings.otlp_endpoint)
    await init_db()
    _stop_event = asyncio.Event()
    _worker_task = asyncio.create_task(queue_worker_loop(_stop_event))
    logger.info("gateway_started", port=settings.port)
    yield
    if _stop_event:
        _stop_event.set()
    if _worker_task:
        await _worker_task
    logger.info("gateway_stopped")


app = FastAPI(
    title="Event Gateway API",
    description="Public-facing API for financial transaction events",
    version="1.0.0",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(TraceIdMiddleware)
instrument_fastapi(app, settings.service_name)
app.include_router(router)


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


@app.get("/health")
@limiter.exempt
async def health(request: Request):
    db_ok = await check_db()
    status_code = 200 if db_ok else 503
    body = {
        "status": "healthy" if db_ok else "unhealthy",
        "service": settings.service_name,
        "database": "connected" if db_ok else "disconnected",
    }
    return JSONResponse(content=body, status_code=status_code)


@app.get("/metrics")
@limiter.exempt
async def metrics(request: Request):
    content, content_type = metrics_response()
    return Response(content=content, media_type=content_type)
