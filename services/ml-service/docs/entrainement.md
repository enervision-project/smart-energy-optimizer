# Entraînement et MLflow

## Prérequis

Depuis un clone à jour du projet, ouvrir un terminal à sa racine. Les commandes
ci-dessous s'exécutent sous Linux ou WSL avec Git, Python 3 standard, Docker et
Docker Compose disponibles. Les dépendances scientifiques sont installées dans
l'image Python 3.12 : aucun venv d'entraînement n'est nécessaire sur le poste.

Récupérer la version des données voulue avec
DVC. Il restitue les trois Parquet ;
le lanceur d'entraînement exige uniquement `.data/ml/splits/train.parquet` et
`.data/ml/splits/validation.parquet`, ignorés par Git.
Voir [Données et préparation](donnees.md) s'ils doivent être générés depuis le CSV.

Le lanceur crée le `.env` depuis `.env.example` s'il manque et initialise un
`JWT_SECRET` absent. Les variables `POSTGRES_USER`, `POSTGRES_PASSWORD` et `POSTGRES_DB`
doivent être renseignées ; les valeurs d'un environnement existant sont conservées.

## Lancer la campagne

```bash
python3 services/ml-service/run_experiments.py
```

Le lanceur :

1. Vérifie les fichiers nécessaires et la disponibilité de Docker.
2. Prépare le `.env` local si nécessaire et relève la version Git du code.
3. Construit l'image `enervision-ml-trainer:local`.
4. Démarre MLflow avec ses dépendances PostgreSQL et attend son état sain.
5. Lance les 96 essais HGB dans `consommation-horaire-sans-meteo-v1`.

Les Parquet sont réutilisés en lecture seule. Seuls train et validation sont montés
dans `ml-trainer`. Le lanceur n'exécute pas `ml-prepare` et ne requiert pas test.

Le serveur MLflow reste disponible après les entraînements. Le processus d'entraînement
occupe le terminal jusqu'à sa fin. Ses étapes et la progression `[01/96]` à `[96/96]`
y sont affichées.

### Prévisualiser

```bash
python3 services/ml-service/run_experiments.py --dry-run
```

Cette option affiche les commandes sans lire les données, créer de configuration,
contacter Docker ou joindre MLflow.

### Identifier et reprendre une campagne

Pour choisir un identifiant lisible :

```bash
python3 services/ml-service/run_experiments.py --campaign-id hgb-sans-meteo-01
```

Sans cette option, le lanceur génère un identifiant unique et l'affiche au démarrage.
Chaque lancement ordinaire démarre une nouvelle campagne.

Après une interruption ou un échec, conserver l'identifiant affiché et reprendre avec :

```bash
python3 services/ml-service/run_experiments.py \
  --campaign-id hgb-sans-meteo-01 \
  --resume
```

`--resume` nécessite `--campaign-id`. Les essais `FINISHED` de cette campagne sont
réutilisés après vérification des empreintes des données et du tag de rechargement
du pipeline. Les essais restants sont exécutés ; les éventuels runs échoués restent
visibles. Utiliser la même version du code, les mêmes configurations et les mêmes
Parquet pour une reprise.

## Quelles expériences sont lancées ?

Le modèle est un `HistGradientBoostingRegressor` commun aux sites. Les variables
communes sont `site_id`, `hour`, `day_of_week`, `month` et `is_working_hours`.

| Tag `feature_variant` | Lags ajoutés  | Nombre d'entrées | Essais |
|-----------------------|---------------|------------------|--------|
| `both_lags`           | 24 h et 168 h | 7                | 24     |
| `lag_24h`             | 24 h          | 6                | 24     |
| `lag_168h`            | 168 h         | 6                | 24     |
| `no_lags`             | Aucun         | 5                | 24     |

La température n'est utilisée dans aucune variante. Le fichier
`configs/hgb_search_no_weather.yaml` définit la grille :

| Paramètre                     | Valeurs comparées                                  |
|-------------------------------|----------------------------------------------------|
| `max_leaf_nodes`              | 31, 63                                             |
| `min_samples_leaf`            | 20, 50, 100                                        |
| `l2_regularization`           | 0, 10                                              |
| `learning_rate` et `max_iter` | 0,1 avec 300 itérations ; 0,05 avec 600 itérations |

Cela représente `2 × 3 × 2 × 2 = 24` configurations par variante, donc 96 essais.

Les paramètres fixes sont `loss=absolute_error`, `early_stopping=false`,
`random_state=42` et `max_bins=255`. La validation n'intervient pas dans `.fit()`.
L'encodage du site est appris sur train puis utilisé avec les catégories natives de
HGB. Les autres entrées passent sans normalisation, avec la gestion native des NULL.

Les anciennes configurations Ridge et HGB avec météo ne sont pas exécutées par
`run_experiments.py`.

## Consulter et comparer dans MLflow

Ouvrir [MLflow local](http://localhost:5000), ou le port configuré par `MLFLOW_PORT`,
puis l'expérience `consommation-horaire-sans-meteo-v1`.
L'identifiant numérique de l'expérience dépend du serveur : rechercher son nom.

1. Filtrer sur le tag `campaign_id` de la campagne.
2. Retenir les runs `FINISHED` et trier `val_macro_nmae_pct` par ordre croissant.
3. Comparer les quatre `feature_variant` et leurs paramètres.
4. Vérifier les résultats par site, l'écart train/validation et les artefacts sauvegardés.

| Mesure                        | Interprétation                                                                                  |
|-------------------------------|-------------------------------------------------------------------------------------------------|
| `val_mae_kwh`                 | Moyenne de l'écart absolu entre consommation réelle et prédite, en kWh. Plus faible = meilleur. |
| `val_rmse_kwh`                | Racine de l'erreur quadratique moyenne, en kWh ; sensible aux erreurs importantes.              |
| `val_macro_nmae_pct`          | Moyenne non pondérée des nMAE des sites ; critère principal de comparaison.                     |
| `val_SITE001_nmae_pct`, etc.  | Erreur normalisée de chaque site, pour repérer une dégradation locale.                          |
| `generalization_gap_nmae_pct` | nMAE macro de validation moins celle de train, en points de pourcentage.                        |
| `val_negative_predictions`    | Nombre de prédictions négatives ; les prédictions ne sont pas écrêtées.                         |

Pour un site, `nMAE = 100 × MAE / moyenne(abs(consommation réelle))`.
Chaque site a le même poids dans la moyenne macro, quelle que soit sa consommation.
Ce n'est pas une MAPE calculée ligne par ligne, ni un pourcentage de prédictions exactes.
La nMAE n'est pas définie pour un site dont la consommation moyenne est nulle.

### Ce qui est enregistré

Chaque run contient notamment :

- Les variables, hyperparamètres, nombre de lignes et empreintes SHA-256 de train et validation.
- Les métriques de train et validation, globales et par site.
- `configuration.json`, `configuration/`, `datasets.json` et `environment.json`.
- `metrics_by_site.json` avec les mesures détaillées.
- `predictions/validation_predictions.parquet` : timestamp, site, cible réelle et prédiction.
- Un modèle MLflow nommé `model` : pipeline sklearn complet, signature et exemple d'entrée.

Le pipeline sauvegardé est rechargé puis ses prédictions de validation sont comparées
à celles calculées avant sauvegarde. Le tag `model_reload_verified=true` confirme ce
contrôle. Les prétraitements sont conservés avec le modèle.

Le meilleur run de la campagne, selon `val_macro_nmae_pct`, reçoit également
`campaign/summary.json` et la configuration de recherche. Le bilan contient les
résultats des essais, le meilleur par variante et les références comparables.

`git_revision`, `git_dirty` et `training_code_sha256`, ainsi que les versions des
bibliothèques, permettent de retrouver le code utilisé. Les schémas de datasets MLflow
décrivent les Parquet complets, température comprise ; le paramètre `features` et la
signature du modèle indiquent les seules colonnes réellement utilisées.

### Résultats de référence du 26 octobre 2026

Campagne : `hgb-no-weather-mvp4v14m`, sur 89 780 lignes de train et 15 083 de validation.

| Variante             | Meilleure nMAE macro validation | MAE validation |
|----------------------|---------------------------------|----------------|
| Lags 24 h et 7 jours | 13,33 %                         | 60,07 kWh      |
| Lag 24 h seul        | 13,12 %                         | 59,26 kWh      |
| Lag 7 jours seul     | 13,08 %                         | 59,10 kWh      |
| Sans lags            | **12,92 %**                     | **58,55 kWh**  |

Le meilleur run de cette campagne est `14a45d446c2e4156847a9f819f81acaa`.
Il utilise les cinq variables communes et les paramètres `learning_rate=0.1`,
`max_iter=300`, `max_leaf_nodes=31`, `min_samples_leaf=100`, `l2_regularization=0`.

Ce bilan décrit une comparaison sur validation, sans évaluation du test ni promotion
automatique. Il ne désigne pas un champion de production.

## Désignation du champion : étape suivante

Le lanceur entraîne, compare et sauvegarde les modèles. Il ne lance pas d'évaluation
sur test et n'enregistre pas automatiquement un champion dans le registry.

La suite consiste à sélectionner un candidat avec la validation et les résultats par
site, puis à effectuer son évaluation finale sur test selon un protocole défini.
Une politique de promotion et une instance MLflow partagée restent à convenir pour
que le choix soit utilisable par l'équipe. Un MLflow local contient uniquement ses
propres runs, même si le code et le nom d'expérience sont identiques.

## Diagnostic rapide

| Symptôme                         | Vérification                                                                                                |
|----------------------------------|-------------------------------------------------------------------------------------------------------------|
| Parquet manquant                 | Récupérer train et validation dans `.data/ml/splits` ; le lanceur ne les génère pas.                        |
| Docker indisponible              | Démarrer Docker et vérifier `docker compose version`.                                                       |
| MLflow ne devient pas sain       | Consulter `docker compose --profile ml logs mlflow-init mlflow db` et vérifier les identifiants PostgreSQL. |
| Campagne déjà existante          | Reprendre avec le même `--campaign-id` et `--resume`, ou choisir un nouvel identifiant.                     |
| Données différentes à la reprise | Restaurer les Parquet de la campagne ou démarrer une autre campagne.                                        |
| Runs absents sur un autre poste  | Vérifier le serveur MLflow ciblé : les runs ne sont pas transférés par Git.                                 |
