import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request

from prediction_service.model import ModelLoadError, Predictor, UnknownSiteError
from prediction_service.registry import available_predictor, changed_champion
from prediction_service.schemas import HealthResponse, PredictRequest, PredictResponse
from prediction_service.settings import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    app.state.predictor = None
    try:
        app.state.predictor = await asyncio.to_thread(
            available_predictor,
            settings.model_dir,
            settings.mlflow_tracking_uri or None,
            settings.registered_model_name,
        )
    except ModelLoadError:
        # the service still starts: /health reports it, /predict returns 503
        logger.exception("aucun modèle chargé")

    async def refresh_loop() -> None:
        if not settings.mlflow_tracking_uri:
            return
        while True:
            await asyncio.sleep(settings.model_refresh_seconds)
            try:
                current = app.state.predictor
                candidate = await asyncio.to_thread(
                    changed_champion,
                    settings.model_dir,
                    settings.mlflow_tracking_uri,
                    settings.registered_model_name,
                    current.version if current else None,
                )
                if candidate is not None:
                    app.state.predictor = candidate
            except Exception:
                logger.exception("Rafraîchissement du champion impossible")

    task = asyncio.create_task(refresh_loop())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


def get_predictor(request: Request) -> Predictor:
    predictor: Predictor | None = request.app.state.predictor
    if predictor is None:
        raise HTTPException(status_code=503, detail="Aucun modèle chargé")
    return predictor


def create_app() -> FastAPI:
    docs = get_settings().enable_docs
    app = FastAPI(
        title="EnerVision Prediction Service",
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

    # sync function: FastAPI runs it in a thread, so inference does not block the loop
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
