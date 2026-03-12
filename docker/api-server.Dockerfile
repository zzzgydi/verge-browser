FROM node:22-bookworm-slim AS admin-web-builder

ENV CI=true

WORKDIR /build

COPY apps/admin-web /build/apps/admin-web

RUN corepack enable && pnpm install --dir /build/apps/admin-web --frozen-lockfile
RUN pnpm --dir /build/apps/admin-web build

FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/apps/api-server

RUN apt-get update && apt-get install -y --no-install-recommends \
    docker-cli \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml /app/pyproject.toml
COPY apps/api-server /app/apps/api-server
COPY packages/python /app/packages/python
COPY --from=admin-web-builder /build/apps/api-server/app/static/admin /app/apps/api-server/app/static/admin

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
