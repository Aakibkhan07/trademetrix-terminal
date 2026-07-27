FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent.py .

ENV LOG_LEVEL=INFO

CMD ["python", "agent.py"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python3 -c "import os, redis; redis.Redis.from_url(os.environ.get('REDIS_URL','redis://redis:6379/0')).ping()"
