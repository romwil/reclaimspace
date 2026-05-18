FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY reclaimspace ./reclaimspace

RUN pip install --no-cache-dir ".[web]"

ENV DATA_DIR=/config
ENV PORT=8777

EXPOSE 8777

VOLUME ["/config"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8777/api/health')" || exit 1

CMD ["python", "-m", "reclaimspace.web"]
