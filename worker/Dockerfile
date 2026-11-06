# Build context: repository root (needs shared/).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY shared /tmp/shared
COPY worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt /tmp/shared && rm -rf /tmp/shared

COPY worker/marketlens_worker ./marketlens_worker

RUN useradd --create-home --uid 10001 app
USER app

# Healthy while the heartbeat file is fresher than 60 seconds.
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import time,sys,pathlib; p=pathlib.Path('/tmp/worker-heartbeat'); sys.exit(0 if p.exists() and time.time()-int(p.read_text())<60 else 1)"

CMD ["python", "-m", "marketlens_worker.main"]
