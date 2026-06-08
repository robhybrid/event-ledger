FROM python:3.13-slim AS base

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml .
COPY ledger_common ./ledger_common
COPY services ./services

RUN uv pip install --system -e .

FROM base AS gateway
ENV GATEWAY_HOST=0.0.0.0
ENV GATEWAY_PORT=8000
ENV GATEWAY_ACCOUNT_SERVICE_URL=http://account-service:8001
ENV GATEWAY_OTLP_ENDPOINT=otel-collector:4317
EXPOSE 8000
CMD ["uvicorn", "services.gateway.app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS account
ENV ACCOUNT_HOST=0.0.0.0
ENV ACCOUNT_PORT=8001
ENV ACCOUNT_OTLP_ENDPOINT=otel-collector:4317
EXPOSE 8001
CMD ["uvicorn", "services.account.app.main:app", "--host", "0.0.0.0", "--port", "8001"]
