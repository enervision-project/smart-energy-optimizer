FROM docker.io/library/python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY requirements.lock .
RUN pip install --no-cache-dir --only-binary :all: --require-hashes -r requirements.lock \
    && useradd --create-home --uid 10001 mlflow \
    && mkdir /mlartifacts \
    && chown mlflow:mlflow /mlartifacts

COPY settings.py init_db.py serve.py smoke_test.py ./
USER mlflow

EXPOSE 5000
CMD ["python", "serve.py"]
