--liquibase formatted sql

--changeset enervision:008-predictions-level-ratio
-- Recalage de niveau (prediction-service, recalibration.py) : prediction_kwh reste la valeur
-- publiée (lue par core-api) ; on garde à côté la prévision brute du champion et le ratio appliqué,
-- pour expliquer chaque valeur et suivre la dérive du modèle seul. NULL pour les lots antérieurs.
ALTER TABLE predictions
    ADD COLUMN model_prediction_kwh NUMERIC(14, 3) CHECK (model_prediction_kwh >= 0),
    ADD COLUMN level_ratio NUMERIC(6, 4) CHECK (level_ratio > 0);
