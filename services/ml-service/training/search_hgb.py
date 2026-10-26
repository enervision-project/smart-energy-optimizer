"""Ablations, variantes de features et grille HGB sur train et validation."""

import argparse
from copy import deepcopy
from hashlib import sha256
from itertools import product
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import os
import re
import uuid

from mlflow import MlflowClient
import yaml

from .data import FEATURES, load_data
from .tracking import connect
from .train import read_config, run


def build_trials(config_path: Path) -> tuple[dict, list[dict], dict]:
    specification = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    base = read_config(config_path.parent / specification["base_config"])
    if base["model"] != "hist_gradient_boosting":
        raise ValueError("La campagne attend un modèle HGB.")
    include_ablations = specification.get("include_ablations", True)
    if not isinstance(include_ablations, bool):
        raise ValueError("include_ablations doit être un booléen.")
    variants = specification.get("feature_variants", {"all_features": base["features"]})
    if not isinstance(variants, dict) or not variants:
        raise ValueError("feature_variants doit contenir au moins une variante.")
    for name, features in variants.items():
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            raise ValueError("Chaque variante doit avoir un nom simple, sans espaces.")
        if (
            not isinstance(features, list) or not features
            or not all(isinstance(feature, str) for feature in features)
            or len(features) != len(set(features))
            or not set(features).issubset(base["features"])
        ):
            raise ValueError(f"Features invalides pour la variante {name}.")
    trials = []

    def append(config: dict, phase: str, variant: str, removed: str = "none") -> None:
        payload = {key: config[key] for key in ["model", "features", "parameters"]}
        key = sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:20]
        config["tags"] = {
            "study_phase": phase, "feature_variant": variant,
            "weather_enabled": str("temperature_celsius" in config["features"]).lower(),
            "removed_feature": removed,
            "excluded_features": ",".join(feature for feature in FEATURES if feature not in config["features"]),
            "trial_index": str(len(trials) + 1), "trial_key": key,
        }
        trials.append(config)

    grid = specification["grid"]
    combinations = list(product(
        grid["max_leaf_nodes"], grid["min_samples_leaf"],
        grid["l2_regularization"], grid["learning_schedule"],
    ))
    prefix = specification.get("run_name_prefix", "HGB_grid")
    for variant, features in variants.items():
        if include_ablations:
            for feature in features:
                config = deepcopy(base)
                config["features"] = [column for column in features if column != feature]
                config["run_name"] = (
                    f"HGB_without_{feature}" if len(variants) == 1
                    else f"HGB_{variant}_without_{feature}"
                )
                append(config, "ablation", variant, feature)

        for index, (leaves, minimum, regularization, schedule) in enumerate(combinations, 1):
            if set(schedule) != {"learning_rate", "max_iter"}:
                raise ValueError("Chaque learning_schedule doit définir learning_rate et max_iter.")
            config = deepcopy(base)
            config["features"] = features.copy()
            config["parameters"].update({
                "max_leaf_nodes": leaves, "min_samples_leaf": minimum,
                "l2_regularization": regularization, **schedule,
            })
            run_prefix = prefix if len(variants) == 1 else f"{prefix}_{variant}"
            config["run_name"] = (
                f"{run_prefix}_{index:02d}_leaves-{leaves}_min-{minimum}_l2-{regularization}"
                f"_lr-{schedule['learning_rate']}_iter-{schedule['max_iter']}"
            )
            append(config, "grid", variant)
    if len({config["tags"]["trial_key"] for config in trials}) != len(trials):
        raise ValueError("La campagne contient des configurations dupliquées.")
    return base, trials, specification


def existing_result(existing, config: dict) -> dict:
    return {
        "model": config["model"], "run_id": existing.info.run_id,
        "features": config["features"], "parameters": config["parameters"],
        "phase": config["tags"]["study_phase"],
        "feature_variant": config["tags"]["feature_variant"],
        "removed_feature": config["tags"]["removed_feature"],
        "train_nmae_pct": existing.data.metrics["train_macro_nmae_pct"],
        "val_nmae_pct": existing.data.metrics["val_macro_nmae_pct"],
        "val_mae_kwh": existing.data.metrics["val_mae_kwh"],
        "val_rmse_kwh": existing.data.metrics["val_rmse_kwh"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Campagne HGB : variantes de features et grille sur train/validation.")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--data-dir", type=Path, default=Path(os.environ.get("TRAINING_DATA_DIR", ".data/ml/splits")))
    parser.add_argument("--tracking-uri", default=os.environ.get("MLFLOW_TRACKING_URI"))
    parser.add_argument("--campaign-id", default=None)
    parser.add_argument("--reference-run-id", default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Afficher le plan sans lire les données ni joindre MLflow.")
    args = parser.parse_args()
    base, trials, specification = build_trials(args.config)
    if args.dry_run:
        print(json.dumps({"trial_count": len(trials), "trials": trials}, ensure_ascii=False))
        return
    campaign = args.campaign_id or f"hgb-{uuid.uuid4().hex}"
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", campaign):
        raise ValueError("campaign-id doit contenir uniquement lettres, chiffres, tirets ou underscores.")
    data = load_data(args.data_dir)
    connect(args.tracking_uri, base["experiment"])
    client = MlflowClient()
    experiment = client.get_experiment_by_name(base["experiment"])
    previous = client.search_runs(
        [experiment.experiment_id], filter_string=f"tags.campaign_id = '{campaign}'", max_results=1000,
    )
    if previous and not args.resume:
        raise ValueError("Cette campagne existe déjà ; utiliser --resume ou un nouvel identifiant.")
    completed = {}
    for previous_run in previous:
        if previous_run.info.status != "FINISHED":
            continue
        if previous_run.data.tags.get("model_reload_verified") != "true":
            raise ValueError("Un run terminé ne possède pas de pipeline vérifié.")
        for name in ["train", "validation"]:
            if previous_run.data.params[f"{name}_sha256"] != data.manifest[name]["sha256"]:
                raise ValueError("Les données ont changé depuis la campagne à reprendre.")
        key = previous_run.data.tags["trial_key"]
        if key in completed:
            raise ValueError("Plusieurs runs terminés correspondent au même essai.")
        completed[key] = previous_run

    reference = None
    if args.reference_run_id:
        reference_run = client.get_run(args.reference_run_id)
        if reference_run.info.status != "FINISHED":
            raise ValueError("Le run de référence doit être terminé.")
        if reference_run.data.params["features"].split(",") != base["features"]:
            raise ValueError("La référence doit utiliser les mêmes features que la configuration de base.")
        for name in ["train", "validation"]:
            if reference_run.data.params[f"{name}_sha256"] != data.manifest[name]["sha256"]:
                raise ValueError("La référence n'a pas utilisé les mêmes données.")
        for name, value in base["parameters"].items():
            if reference_run.data.params.get(name) != str(value):
                raise ValueError(f"Paramètre de référence différent : {name}")
        reference = {
            "run_id": reference_run.info.run_id,
            "val_nmae_pct": reference_run.data.metrics["val_macro_nmae_pct"],
        }

    results = []
    with TemporaryDirectory(prefix="hgb-campaign-") as temporary:
        for index, config in enumerate(trials, 1):
            key = config["tags"]["trial_key"]
            if key in completed:
                result = existing_result(completed[key], config)
                state = "repris"
            else:
                path = Path(temporary) / f"{index:02d}.yaml"
                path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
                outcome = run(path, args.data_dir, args.tracking_uri, campaign)
                result = {
                    "model": config["model"], "run_id": outcome["run_id"],
                    "features": config["features"], "parameters": config["parameters"],
                    "phase": config["tags"]["study_phase"],
                    "feature_variant": config["tags"]["feature_variant"],
                    "removed_feature": config["tags"]["removed_feature"],
                    "train_nmae_pct": outcome["train"]["macro_nmae_pct"],
                    "val_nmae_pct": outcome["validation"]["macro_nmae_pct"],
                    "val_mae_kwh": outcome["validation"]["mae_kwh"],
                    "val_rmse_kwh": outcome["validation"]["rmse_kwh"],
                }
                state = "terminé"
            results.append(result)
            print(
                f"[{index:02d}/{len(trials)}] {state} {config['run_name']} "
                f"nMAE validation={result['val_nmae_pct']:.4f}% run={result['run_id']}",
                flush=True,
            )

    baseline = next(
        result for result in results if result["phase"] == "grid"
        and result["features"] == base["features"] and result["parameters"] == base["parameters"]
    )
    reference = reference or {"run_id": baseline["run_id"], "val_nmae_pct": baseline["val_nmae_pct"]}
    best_grid = min((item for item in results if item["phase"] == "grid"), key=lambda item: item["val_nmae_pct"])
    best_ablation = min(
        (item for item in results if item["phase"] == "ablation"),
        key=lambda item: item["val_nmae_pct"], default=None,
    )
    variant_names = list(dict.fromkeys(item["feature_variant"] for item in results))
    best_by_variant = {
        variant: min(
            (item for item in results if item["phase"] == "grid" and item["feature_variant"] == variant),
            key=lambda item: item["val_nmae_pct"],
        )
        for variant in variant_names
    }
    reference_by_variant = {
        variant: next(
            item for item in results if item["phase"] == "grid"
            and item["feature_variant"] == variant and item["parameters"] == base["parameters"]
        )
        for variant in variant_names
    }
    summary = {
        "campaign_id": campaign, "experiment_id": experiment.experiment_id,
        "reference": reference, "repeated_reference": baseline,
        "datasets": data.manifest, "specification": specification,
        "trial_count": len(results), "results": results,
        "best_grid": best_grid, "best_ablation": best_ablation,
        "best_by_variant": best_by_variant, "reference_by_variant": reference_by_variant,
    }
    client.log_dict(best_grid["run_id"], summary, "campaign/summary.json")
    client.log_artifact(best_grid["run_id"], str(args.config), artifact_path="campaign")
    print("SUMMARY_JSON " + json.dumps({
        "campaign_id": campaign, "trial_count": len(results),
        "reference": reference, "repeated_reference": baseline,
        "ablation": [item for item in results if item["phase"] == "ablation"],
        "best_grid": best_grid, "best_ablation": best_ablation,
        "best_by_variant": best_by_variant, "reference_by_variant": reference_by_variant,
        "summary_run_id": best_grid["run_id"],
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
