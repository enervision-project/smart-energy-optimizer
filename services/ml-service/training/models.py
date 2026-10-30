from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler


def build_pipeline(family: str, features: list[str], parameters: dict) -> tuple[Pipeline, dict]:
    if family == "hist_gradient_boosting":
        site = ["site_id"] if "site_id" in features else []
        numeric = [column for column in features if column not in site]
        preprocessing = ColumnTransformer(
            [
                ("site", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1), site),
                ("numeric", "passthrough", numeric),
            ],
            sparse_threshold=0,
        )
        estimator = HistGradientBoostingRegressor(
            categorical_features=[0] if site else [], **parameters,
        )
        description = {
            "site_encoding": "ordinal + native categorical" if site else "not used",
            "calendar_encoding": "numeric",
            "imputation": "native missing values",
            "scaling": "none",
        }
    elif family == "ridge":
        categorical = [column for column in features if column in {"site_id", "hour", "day_of_week", "month"}]
        numeric = [column for column in features if column not in categorical]
        preprocessing = ColumnTransformer(
            [
                ("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=True), categorical),
                ("numeric", Pipeline([
                    ("impute", SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)),
                    ("scale", StandardScaler()),
                ]), numeric),
            ],
            sparse_threshold=1.0,
        )
        estimator = Ridge(**parameters)
        description = {
            "site_encoding": "one-hot",
            "calendar_encoding": "one-hot",
            "imputation": "train median + missing indicators",
            "scaling": "StandardScaler on numeric features",
            "interactions": "none",
        }
    else:
        raise ValueError(f"Modèle inconnu : {family}")
    return Pipeline([("preprocessing", preprocessing), ("model", estimator)]), description
