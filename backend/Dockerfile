# OpenClaw Observatory backend (Mission M002).
#
# Security posture (docs/security.md §8, §15):
# - official, version-pinned base image;
# - non-root runtime user;
# - pinned dependencies, no cache, no build tools in the final layer set;
# - serves plain HTTP and is designed to sit behind a reverse proxy / tailnet
#   for TLS ("HTTPS-ready": uvicorn trusts X-Forwarded-* via --proxy-headers).

FROM python:3.13.5-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Dedicated unprivileged user (no shell, no home-directory privileges).
RUN groupadd --gid 10001 observatory \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin observatory

WORKDIR /srv/observatory

# Install pinned dependencies first for build-layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY migrations ./migrations

USER observatory

EXPOSE 8000

# Container-level liveness probe against /health (stdlib only; no curl in slim).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"]

# --factory: build_app validates configuration before binding (M003.5 §2).
CMD ["uvicorn", "--factory", "app.main:build_app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
