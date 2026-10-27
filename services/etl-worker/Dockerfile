# Contexte de build : racine du dépôt.
FROM docker.io/library/python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        cron \
        tzdata \
        util-linux \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --no-create-home appuser

ENV PYTHONUNBUFFERED=1 TZ=Europe/Paris

RUN ln -snf /usr/share/zoneinfo/Europe/Paris /etc/localtime \
    && echo Europe/Paris > /etc/timezone

WORKDIR /app

COPY services/etl-worker/ .

RUN pip install --no-cache-dir . \
    && install -m 0644 cron/etl /etc/cron.d/etl \
    && install -m 0755 cron/start.sh /usr/local/bin/etl-cron-start \
    && install -m 0755 cron/job.sh /usr/local/bin/etl-cron-job \
    && install -d -o appuser -g appuser -m 0750 /run/etl-worker

CMD ["/usr/local/bin/etl-cron-start"]
