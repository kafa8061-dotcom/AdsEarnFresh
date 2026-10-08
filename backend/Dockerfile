FROM python:3.14.3-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENVIRONMENT=production \
    PORT=8000 \
    WEB_CONCURRENCY=2 \
    GRACEFUL_SHUTDOWN_SECONDS=30 \
    FORWARDED_ALLOW_IPS=127.0.0.1

WORKDIR /srv/adsearn
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app
RUN useradd --create-home --system appuser
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import os,urllib.request; host=os.getenv('ALLOWED_HOSTS','localhost').split(',')[0].strip(); req=urllib.request.Request('http://127.0.0.1:'+os.getenv('PORT','8000')+'/health/live', headers={'Host':host}); urllib.request.urlopen(req, timeout=3)"]
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"${PORT}\" --workers \"${WEB_CONCURRENCY}\" --proxy-headers --forwarded-allow-ips \"${FORWARDED_ALLOW_IPS}\" --timeout-graceful-shutdown \"${GRACEFUL_SHUTDOWN_SECONDS}\" --no-access-log"]
