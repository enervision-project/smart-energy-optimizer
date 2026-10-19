# Contexte de build : racine du dépôt (docker build -f services/etl-worker/Dockerfile .)
FROM docker.io/library/python:3.12-slim
WORKDIR /app
COPY services/etl-worker/ .
RUN pip install --no-cache-dir .
ENV PYTHONUNBUFFERED=1
CMD ["etl-worker"]
