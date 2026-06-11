FROM python:3.11-slim

COPY requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements.lock

COPY . /app
WORKDIR /app
RUN addgroup --system app && adduser --system --ingroup app app && chown -R app:app /app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"

USER app
# Single worker by design: session history, pending confirm-actions, the LLM/
# retriever caches and the circuit breaker live in process memory and are NOT
# shared across workers/replicas. Running >1 worker breaks confirm-action flows
# and session continuity. See README "Deployment topology" before scaling out;
# scaling requires moving that state to Redis/Postgres first.
CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
