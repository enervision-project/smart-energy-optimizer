# Contexte de build : racine du dépôt.
FROM docker.io/library/python:3.12-slim
# libgomp1 : runtime OpenMP requis par XGBoost
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --no-create-home appuser \
    && mkdir /models && chown appuser /models
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 MODEL_DIR=/models PYTHONPATH=/app
WORKDIR /app
COPY services/prediction-service/pyproject.toml ./
COPY services/prediction-service/src ./src
RUN pip install --no-cache-dir .
COPY services/ml-service/training ./training
COPY services/ml-service/configs ./configs
USER appuser
EXPOSE 8000
CMD ["prediction-service"]
