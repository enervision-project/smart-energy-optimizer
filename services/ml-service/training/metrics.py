"""Mêmes mesures et mêmes lignes pour les deux familles de modèles."""

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error

from .data import TARGET


def _scores(actual: np.ndarray, predicted: np.ndarray) -> dict:
    mae = float(mean_absolute_error(actual, predicted))
    denominator = float(np.mean(np.abs(actual)))
    return {
        "rows": len(actual),
        "mae_kwh": mae,
        "rmse_kwh": float(root_mean_squared_error(actual, predicted)),
        "r2": float(r2_score(actual, predicted)) if len(actual) > 1 else None,
        "nmae_pct": 100 * mae / denominator if denominator else None,
        "negative_predictions": int(np.sum(predicted < 0)),
    }


def evaluate(frame: pd.DataFrame, prediction: np.ndarray) -> dict:
    prediction = np.asarray(prediction, dtype=float)
    if prediction.shape != (len(frame),) or not np.isfinite(prediction).all():
        raise ValueError("Les prédictions doivent être finies et alignées sur toutes les lignes.")
    values = frame[["site_id", TARGET]].copy()
    values["prediction"] = prediction
    by_site = {
        str(site): _scores(group[TARGET].to_numpy(), group.prediction.to_numpy())
        for site, group in values.groupby("site_id", observed=True, sort=True)
    }
    normalized = [report["nmae_pct"] for report in by_site.values()]
    aggregate = _scores(values[TARGET].to_numpy(), prediction)
    # Un site à cible toujours nulle rend la macro non définie, sans l'exclure silencieusement.
    aggregate["macro_nmae_pct"] = (
        float(np.mean(normalized)) if all(value is not None for value in normalized) else None
    )
    return {"global": aggregate, "by_site": by_site}


def flatten_metrics(prefix: str, report: dict) -> dict[str, float]:
    result = {
        f"{prefix}_{name}": float(value)
        for name, value in report["global"].items() if value is not None
    }
    for site, scores in report["by_site"].items():
        result.update({
            f"{prefix}_{site}_{name}": float(value)
            for name, value in scores.items() if value is not None
        })
    return result
