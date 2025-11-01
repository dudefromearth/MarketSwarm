FROM python:3.12-slim
RUN apt-get update && apt-get install -y tini && rm -rf /var/lib/apt/lists/*
WORKDIR /ws
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd -m appuser && chown -R appuser /ws
USER appuser
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-u", "main.py"]