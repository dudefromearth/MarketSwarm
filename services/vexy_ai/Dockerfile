FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends tini ca-certificates \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

USER nobody
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["/usr/bin/tini", "-g", "-e", "143", "--"]
CMD ["python", "-u", "main.py"]