"""Application FastAPI : /predict et /health."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request

from ml_engine.model import ModelLoadError, Predictor, UnknownSiteError, load_predictor
from ml_engine.schemas import HealthResponse, PredictRequest, PredictResponse
from ml_engine.settings import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    app.state.predictor = None
    try:
        app.state.predictor = load_predictor(settings.model_dir)
    except ModelLoadError:
        # le service démarre quand même : /health l'indique, /predict répond 503
        logger.exception("aucun modèle chargé")
    yield


def get_predictor(request: Request) -> Predictor:
    predictor: Predictor | None = request.app.state.predictor
    if predictor is None:
        raise HTTPException(status_code=503, detail="Aucun modèle chargé")
    return predictor


def create_app() -> FastAPI:
    docs = get_settings().enable_docs
    app = FastAPI(
        title="EnerVision ML Engine",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
    )

    @app.get("/health", response_model=HealthResponse)
    def health(request: Request) -> HealthResponse:
        predictor: Predictor | None = request.app.state.predictor
        return HealthResponse(
            status="ok" if predictor else "degraded",
            model_loaded=predictor is not None,
            model_version=predictor.version if predictor else None,
        )

    # fonction synchrone : FastAPI l'exécute dans un thread, l'inférence ne bloque pas la boucle
    @app.post("/predict", response_model=PredictResponse)
    def predict(
        payload: PredictRequest, predictor: Annotated[Predictor, Depends(get_predictor)]
    ) -> PredictResponse:
        try:
            value = predictor.predict(payload)
        except UnknownSiteError as exc:
            raise HTTPException(status_code=422, detail=f"Site inconnu du modèle : {exc}") from exc
        return PredictResponse(prediction=value, model_version=predictor.version)

    return app


app = create_app()
