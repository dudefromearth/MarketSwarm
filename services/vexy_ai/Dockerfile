FROM python:3.12-slim

ARG UID=10001
ARG GID=10001

RUN apt-get update && apt-get install -y --no-install-recommends tini ca-certificates \
  && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    if getent group "${GID}" >/dev/null; then grp="$(getent group "${GID}" | cut -d: -f1)"; \
    else grp=app; groupadd -g "${GID}" "${grp}"; fi; \
    useradd -m -u "${UID}" -g "${grp}" -s /bin/bash app

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
ENV PYTHONPATH=/app/src

USER app
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["/usr/bin/tini","-g","-e","143","--"]
CMD ["python","-u","-m","vexy_ai"]