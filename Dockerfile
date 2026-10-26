# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run check && npm run build

FROM node:22-bookworm-slim AS codex
ARG CODEX_VERSION=0.164.0
RUN npm install -g --omit=dev @openai/codex@${CODEX_VERSION}

FROM python:3.12-slim-bookworm AS package
WORKDIR /src
COPY pyproject.toml README.md ARCHITETTURA.md ./
COPY alterecho ./alterecho
COPY --from=web /alterecho/static ./alterecho/static
RUN pip wheel --no-cache-dir --wheel-dir /wheels '.[server]'

FROM python:3.12-slim-bookworm AS runtime
ARG VERSION=development
ARG REVISION=local
ARG SOURCE=https://github.com/giovannirob/AlterEcho
LABEL org.opencontainers.image.title="AlterEcho" \
    org.opencontainers.image.description="Headless AI conversation server with CLI and Web clients" \
    org.opencontainers.image.source=$SOURCE \
    org.opencontainers.image.version=$VERSION \
    org.opencontainers.image.revision=$REVISION
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    ALTERECHO_HOME=/var/lib/alterecho CODEX_HOME=/var/lib/alterecho-codex \
    ALTERECHO_HOST=0.0.0.0 ALTERECHO_PORT=8765 \
    ALTERECHO_ORIGINS=http://127.0.0.1:8765,http://localhost:8765 \
    ALTERECHO_ALLOWED_HOSTS=127.0.0.1,localhost,alterecho
RUN groupadd --gid 10001 alterecho && useradd --uid 10001 --gid 10001 --create-home alterecho \
    && mkdir -p /var/lib/alterecho /var/lib/alterecho-codex \
    && chown -R 10001:10001 /var/lib/alterecho /var/lib/alterecho-codex
COPY --from=package /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels 'alterecho[server]' && rm -rf /wheels
COPY --from=codex /usr/local/bin/node /usr/local/bin/node
COPY --from=codex /usr/local/lib/node_modules/@openai /opt/node_modules/@openai
RUN ln -s /opt/node_modules/@openai/codex/bin/codex.js /usr/local/bin/codex
USER 10001:10001
WORKDIR /var/lib/alterecho
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/v1/health',timeout=3).read()"]
STOPSIGNAL SIGTERM
CMD ["alterecho", "serve", "--foreground"]
