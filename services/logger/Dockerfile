FROM python:3.12-slim

WORKDIR /app

# Install only what we need
RUN pip install --no-cache-dir redis==5.0.4

# Minimal heartbeat-only app
COPY main.py /app/main.py

# No tini, no extras — keep it simple
CMD ["python", "-u", "/app/main.py"]