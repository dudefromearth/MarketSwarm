FROM python:3.12-slim

ARG UID=10001
ARG GID=10001

RUN apt-get update && apt-get install -y --no-install-recommends tini ca-certificates curl \
  && rm -rf /var/lib/apt/lists/*

# Reuse existing group if GID exists; otherwise create it, then create user
RUN set -eux; \
    if getent group "${GID}" >/dev/null; then grp="$(getent group "${GID}" | cut -d: -f1)"; \
    else grp=app; groupadd -g "${GID}" "${grp}"; fi; \
    useradd -m -u "${UID}" -g "${grp}" -s /bin/bash app

WORKDIR /app
COPY requirements.txt .
# requirements can be empty for heartbeat-only; keep for future REST/WS work
RUN pip install --no-cache-dir -r requirements.txt || true

COPY . .
USER app
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["/usr/bin/tini","-g","-e","143","--"]
# ← run the simple entrypoint directly
CMD ["python","-u","/app/main.py"]