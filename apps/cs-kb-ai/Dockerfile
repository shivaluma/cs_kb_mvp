FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8090

WORKDIR /app

RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates curl \
  && rm -rf /var/lib/apt/lists/* \
  && addgroup --system app \
  && adduser --system --ingroup app app

COPY requirements.txt .
RUN python -m venv /opt/venv \
  && /opt/venv/bin/pip install --upgrade pip \
  && /opt/venv/bin/pip install -r requirements.txt

COPY app app
RUN chown -R app:app /app

USER app
ENV PATH="/opt/venv/bin:${PATH}"
EXPOSE 8090
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c 'import os, urllib.request; urllib.request.urlopen("http://127.0.0.1:%s/healthz" % os.getenv("PORT", "8090"), timeout=3).read()' || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8090} --proxy-headers"]
