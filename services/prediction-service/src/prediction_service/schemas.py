"""Contrat de l'API : une ligne de features par prédiction."""

from pydantic import BaseModel, ConfigDict, Field


class PredictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_id: str = Field(
        pattern=r"^SITE_\d{3,}$", description="Identifiant du site (SITE_001, SITE_002…)."
    )
    hour: int = Field(ge=0, le=23, description="Heure de la journée.")
    day_of_week: int = Field(ge=0, le=6, description="Jour de la semaine, lundi = 0.")
    month: int = Field(ge=1, le=12, description="Mois de l'année.")
    lag_24h: float | None = Field(
        default=None,
        ge=0,
        description="Consommation du site à la même heure la veille ; absente = valeur manquante.",
    )
    lag_168h: float | None = Field(
        default=None,
        ge=0,
        description="Consommation du site à la même heure 7 jours avant ; absente = manquante.",
    )
    temperature_celsius: float | None = Field(
        default=None,
        ge=-60,
        le=60,
        description="Température prévue ; absente = valeur manquante pour le modèle.",
    )
    is_working_hours: int = Field(ge=0, le=1, description="1 = heure de travail, 0 sinon.")


class PredictResponse(BaseModel):
    prediction: float = Field(description="Consommation prévue (unité de la cible d'entraînement).")
    model_version: str


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    model_version: str | None = None
