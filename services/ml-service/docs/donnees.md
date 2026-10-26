# Données et préparation

## Sources et exploration

Les sources historiques se récupèrent séparément de Git et se placent ainsi :

```text
.data/ml/
├── raw/
│   ├── all_sites_combined.csv
│   └── metadata/
│       ├── SITE001_metadata.json
│       ├── ...
│       └── SITE007_metadata.json
└── splits/
    ├── train.parquet
    ├── validation.parquet
    └── test.parquet
```

Le CSV contient les consommations horaires des sites. Une ligne datée de 10 h correspond
à l'intervalle 10 h–11 h. La préparation conserve les horodatages de la source sans
conversion horaire.

Le notebook `01_exploration_consommation.ipynb` sert à examiner les valeurs manquantes,
les profils par site, les rythmes calendaires, l'autocorrélation et les variables météo.
Les décisions sur les variables doivent s'appuyer sur train ; validation sert à comparer
les configurations et test reste réservé à l'évaluation finale.

Le CSV d'origine n'est pas modifié. Les métadonnées fournissent le planning de chaque
site dans `profile.working_hours` et `profile.working_days`.

## Préparation effectuée par Python

`training/prepare_data.py` applique les étapes suivantes :

1. Lire le CSV et les métadonnées de chacun des sites présents.
2. Vérifier les dates, l'absence de doublons `(site_id, timestamp)` et la cohérence de
   `hour`, `day_of_week` et `month` avec le timestamp ; trier les lignes.
3. Recalculer `is_working_hours` à partir du planning du site.
4. Chercher les consommations du même site exactement 24 h et 168 h auparavant.
5. Exclure les lignes dont la cible `consumption_kwh` est NULL.
6. Conserver le schéma prévu, vérifier les valeurs et découper chronologiquement.
7. Vérifier les fichiers préparés avant de remplacer les trois Parquet de sortie.

Les lags sont calculés avant la suppression des cibles NULL, pour conserver les trous
dans l'historique. Une recherche par site et timestamp est utilisée : ce n'est pas un
décalage de 24 ou 168 lignes, qui serait incorrect si des heures manquent.

### Horaires travaillés

`is_working_hours` vaut 1 si les deux conditions sont réunies :

- le jour est présent dans `working_days` (`0` = lundi, `6` = dimanche) ;
- l'heure appartient à `[début, fin)` dans `working_hours`.

Avec `[8, 19]` et `[0, 1, 2, 3, 4]`, le flag vaut 1 du lundi au vendredi, de 8 h
incluse à 19 h exclue. Il vaut 0 le week-end. Un planning `[0, 24]` avec les sept jours
donne 1 à toute heure, notamment pour les sites fonctionnant en continu.

### Schéma des Parquet

L'ordre des colonnes est vérifié par `training/data.py`.

| Colonne | Utilisation |
| --- | --- |
| `timestamp` | Clé temporelle, découpage et alignement des prédictions ; pas une entrée directe du modèle. |
| `site_id` | Identification du site ; encodage catégoriel dans le pipeline. |
| `hour` | Heure, de 0 à 23. |
| `day_of_week` | Jour de la semaine, de 0 à 6. |
| `month` | Mois, de 1 à 12. |
| `is_working_hours` | Flag 0/1 recalculé depuis les métadonnées. |
| `lag_24h` | Consommation du même site à la même heure la veille. |
| `lag_168h` | Consommation du même site à la même heure sept jours auparavant. |
| `temperature_celsius` | Conservée dans le schéma existant, exclue de la campagne sans météo. |
| `consumption_kwh` | Cible à prévoir ; aucune valeur NULL conservée. |

Le modèle utilise les cinq variables communes `site_id`, `hour`, `day_of_week`, `month`
et `is_working_hours`, puis zéro, un ou deux lags selon la variante. Le calendrier décrit
les rythmes quotidiens, hebdomadaires et saisonniers ; le site distingue les profils
de consommation et le flag ajoute son planning propre. Les lags permettent de tester
l'apport de la consommation passée, sans présumer qu'une corrélation améliore la prévision.

La campagne exclut la température car elle ne sera pas disponible pour les prévisions.
L'humidité et le rayonnement solaire ne font pas partie de ces Parquet. La présence
d'une colonne dans le fichier ne signifie pas qu'elle est fournie au modèle : la liste
`features` de la configuration sélectionne ses entrées.

### Valeurs manquantes et contrôles

La cible, le site, le timestamp et les variables calendaires doivent être présents.
Les lags peuvent rester NULL si la mesure historique manque, notamment au début de
l'historique. HGB traite ces valeurs manquantes nativement ; elles ne sont remplacées
ni par zéro ni par une valeur calculée sur validation.

Le chargement refuse notamment les doublons, les consommations négatives, les valeurs
infinies, les calendriers incohérents et les jeux vides. Les mêmes sites doivent être
présents dans chaque jeu. Les variantes sont comparées sur les mêmes lignes, sans
supprimer des observations selon les lags sélectionnés.

## Découpage chronologique

| Jeu | Début inclus | Fin exclue | Rôle |
| --- | --- | --- | --- |
| Train | 2023-01-01 | 2024-07-01 | Apprendre les prétraitements et le modèle. |
| Validation | 2024-07-01 | 2024-10-01 | Comparer les variables et hyperparamètres. |
| Test | 2024-10-01 | 2025-01-01 | Évaluer finalement le candidat retenu. |

Il n'y a pas de mélange aléatoire. Les lags d'une ligne utilisent une consommation
antérieure, éventuellement située dans la période précédente. Les lags 24 h et 7 jours
se réfèrent à des heures déjà terminées au début de la journée à prévoir ; le script
vérifie cette condition. Une mesure historique absente reste une valeur manquante.

## Récupérer ou générer les Parquet

Pour reproduire une campagne existante, récupérer ses Parquet train et validation
permet de conserver exactement les mêmes fichiers. Le lanceur d'entraînement ne demande
ni CSV ni métadonnées lorsque les deux Parquet sont déjà disponibles. Le fichier test
n'est ni requis ni monté dans le conteneur d'entraînement.

Pour préparer les jeux sur un nouveau poste à partir des sources, exécuter les commandes
suivantes depuis la racine, sous Linux/WSL, avec Docker démarré.

Les appels directs à Compose nécessitent un `.env` valide. S'il n'existe pas encore :

```bash
cp .env.example .env
openssl rand -base64 32
```

Copier la valeur générée dans `JWT_SECRET` du `.env`. Renseigner `POSTGRES_USER`,
`POSTGRES_PASSWORD` et `POSTGRES_DB` ; conserver les identifiants déjà utilisés si une
base locale existe. Le secret est nécessaire à la validation de la configuration
Compose, même si l'API n'est pas démarrée.

Déposer le CSV et les sept métadonnées, puis préparer le dossier de sortie et l'image :

```bash
mkdir -p .data/ml/splits

docker compose \
  -f compose.yaml \
  -f services/ml-service/compose.training.yaml \
  --profile preparation \
  build ml-prepare
```

Générer les trois fichiers avec les droits de l'utilisateur du poste :

```bash
docker compose \
  -f compose.yaml \
  -f services/ml-service/compose.training.yaml \
  --profile preparation \
  run --rm --no-deps \
  --user "$(id -u):$(id -g)" \
  ml-prepare
```

Cette commande crée ou remplace **train, validation et test** dans `.data/ml/splits`.
Elle ne lance aucun entraînement. Elle est distincte du
[lanceur des 96 essais](entrainement.md#lancer-la-campagne), qui ne régénère aucun Parquet.
