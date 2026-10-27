# Spécification technique — ML Engine, MLflow Model Registry et AWS S3

> **Document à fournir à une IA de développement.** Objectif : analyser le dépôt existant et préparer, puis implémenter, les changements nécessaires **sans réécrire inutilement l'architecture actuelle**. Ne pas inventer les noms de modules, endpoints ou variables : les découvrir dans le code et adapter les propositions.

## 1. Contexte existant

- L'application est déployée sur une instance **AWS EC2** et est composée de plusieurs services.
- Un service **`ml-engine`** est déjà responsable de l'orchestration ML, du chargement du **modèle champion** et des entraînements de modèles concurrents (*challengers*).
- Une API **FastAPI** utilise le champion pour effectuer des prédictions.
- **MLflow** existe dans l'écosystème et servira au suivi des entraînements et au **Model Registry**.
- Un bucket **Amazon S3 existe déjà** et doit être réutilisé pour le stockage durable des artefacts de modèles.
- **Décision d'architecture : MLflow reste démarré en permanence.** Ne pas implémenter de mécanisme pour démarrer/arrêter MLflow à chaque entraînement.
- Une session d'entraînement planifiée doit s'exécuter **chaque jour à 01:00**.
- Après un redéploiement / redémarrage de `ml-engine`, il faut vérifier MLflow, récupérer la date du dernier **entraînement réussi**, et déclencher un entraînement de rattrapage si celui-ci remonte à **plus de 25 heures (1 jour + 1 heure)**, ou s'il n'y a encore jamais eu d'entraînement réussi.

## 2. Objectifs fonctionnels

1. **Disponibilité des prédictions :** FastAPI doit pouvoir servir les prédictions avec le champion déjà chargé, même pendant l'entraînement et l'enregistrement d'un challenger.
2. **Persistance :** les poids/fichiers réels de chaque version de modèle doivent être enregistrés dans **S3** en tant qu'artefacts MLflow, et les métadonnées du Registry dans un **backend persistant compatible MLflow** (SQLite persistant pour petit déploiement ou PostgreSQL, selon l'existant).
3. **Versionnement :** enregistrer les modèles sous un nom de modèle stable, avec des versions dans le **MLflow Model Registry**.
4. **Identification du champion :** utiliser l'alias MLflow **`champion`** (plutôt que les anciens *stages*). Le nom exact du modèle enregistré est configurable.
5. **Évaluation :** le challenger ne remplace le champion qu'après validation des critères métier et techniques. Si aucun champion n'existe, le premier modèle valide devient champion.
6. **Ordonnancement :** entraîner chaque jour à **01:00 heure locale explicite**, configurable avec un fuseau IANA (par défaut à confirmer : `Europe/Paris`). Gérer le changement d'heure de manière documentée.
7. **Rattrapage au démarrage :** si dernier entraînement réussi > 25 heures, déclencher **une seule** session de rattrapage de manière asynchrone, sans bloquer le démarrage de l'API ni empêcher le chargement du champion existant.
8. **Robustesse :** éviter tout entraînement concurrent ou en double dû au cron, à un redéploiement, aux retries ou à plusieurs réplicas/processus.
9. **Observabilité :** logs et métriques d'état (MLflow, dernier succès, entraînement actif, champion chargé, version, échecs).

## 3. Architecture cible

```text
                       AWS EC2
  ┌───────────────────────────────────────────────────┐
  │                                                   │
  │  ┌────────────────┐    champion/refresh            │
  │  │   ml-engine    │────────────────────────────┐   │
  │  │ - scheduler    │                            │   │
  │  │ - orchestration│                            ▼   │
  │  │ - training     │                    ┌───────────────┐
  │  │ - validation   │                    │    FastAPI    │
  │  └───────┬────────┘                    │  /predict     │
  │          │                             │ modèle en RAM │
  │          ▼                             └──────┬────────┘
  │  ┌─────────────────────┐                      │
  │  │ MLflow (toujours ON)│                      │
  │  │ Tracking + Registry │◄─────────────────────┘
  │  └─────────┬───────────┘       chargement version
  │            │
  │     ┌──────┴───────────────┐
  │     ▼                      ▼
  │ backend persistant       Amazon S3 existant
  │ métadonnées             artefacts de modèles
  │ SQLite / PostgreSQL     s3://bucket/mlflow-artifacts/
  └───────────────────────────────────────────────────┘
```

> **Séparation de responsabilités :** MLflow est le catalogue et système de suivi ; S3 stocke les artefacts ; `ml-engine` décide de l'entraînement, des évaluations et de la promotion ; FastAPI fait l'inférence. Ne pas faire dépendre chaque prédiction d'une requête MLflow/S3.

## 4. Persistance MLflow et configuration AWS

### 4.1. Stockage

- Configurer MLflow avec un **backend SQL persistant** pour les expériences, runs, métriques, versions et aliases du Registry.
- Configurer le stockage des artefacts vers un **préfixe dédié dans le bucket S3 existant** : `s3://<BUCKET_EXISTANT>/<PREFIX_MLFLOW>/`.
- Stocker les artefacts MLflow **dans leur format natif** (répertoire `MLmodel`, poids ou modèle sérialisé, dépendances, etc.) ; aucune compression ZIP/TAR obligatoire.
- Le chemin exact des objets S3 dépend de MLflow et de la stratégie d'artefacts : **ne pas supposer une arborescence fixe** ; lire les URI retournées par MLflow.
- Ne pas faire de la base SQLite un fichier temporaire à l'intérieur d'un conteneur éphémère ; utiliser un volume persistant. Préférer PostgreSQL si accès concurrents et besoin de robustesse.
- Définir des sauvegardes adaptées à la base de métadonnées et des règles de rétention sur S3 ; éviter la suppression d'un champion ou d'une version encore référencée.

### 4.2. Exemple conceptuel de configuration

```env
MLFLOW_TRACKING_URI=http://mlflow:5000
MLFLOW_REGISTERED_MODEL_NAME=<NOM_DU_MODELE>
MLFLOW_CHAMPION_ALIAS=champion
MLFLOW_ARTIFACT_ROOT=s3://<BUCKET_EXISTANT>/mlflow-artifacts/
MLFLOW_BACKEND_STORE_URI=<URI_SQL_PERSISTANTE>
TRAINING_TIME=01:00
TRAINING_TIMEZONE=Europe/Paris
TRAINING_STALE_AFTER_HOURS=25
MODEL_CACHE_DIR=/var/lib/app/models
```

Commande illustrative (à adapter à la version MLflow et au mode de déploiement existant) :

```bash
mlflow server \
  --host 0.0.0.0 \
  --port 5000 \
  --backend-store-uri "$MLFLOW_BACKEND_STORE_URI" \
  --artifacts-destination "$MLFLOW_ARTIFACT_ROOT" \
  --serve-artifacts
```

- Authentifier/protéger le service MLflow sur réseau privé ; **ne pas exposer le port 5000 publiquement sans contrôle d'accès**.
- Utiliser le **rôle IAM de l'instance EC2** (ou du service) pour autoriser les accès S3 nécessaires, avec privilèges minimaux, plutôt que des clés AWS statiques.
- Utiliser des secrets gérés pour les identifiants SQL. Vérifier les permissions `s3:ListBucket` limitées au préfixe utile et `s3:GetObject` / `s3:PutObject` (+ suppression uniquement si nécessaire).
- Vérifier quel mécanisme d'accès aux artefacts est déjà utilisé : proxification des artefacts par MLflow ou accès direct S3 par les clients. Préserver la cohérence de cette configuration.

## 5. Cycle de vie du champion et des challengers

### 5.1. Au démarrage de `ml-engine`

1. Initialiser les dépendances et la configuration.
2. Vérifier la **disponibilité réelle de MLflow** avec des retries à délai borné (et idéalement un healthcheck dans l'orchestrateur). MLflow doit normalement déjà fonctionner : **le vérifier, pas le démarrer à la demande**.
3. Récupérer l'alias `champion` pour le modèle configuré, s'il existe.
4. Demander à FastAPI de charger le champion (ou de restaurer un champion précédemment mis en cache). La logique exacte dépend de l'architecture réelle : chargement direct, appel interne sécurisé, événement, etc.
5. Rechercher la date/heure du **dernier entraînement réussi**, dans une source persistante. Distinguer le dernier run quelconque du dernier **run de training réussi** : un run d'évaluation, un run échoué ou une tentative avortée ne doit pas réinitialiser l'horloge.
6. Si aucun entraînement réussi n'est trouvé **ou si `now_utc - last_success_utc > 25 h`**, demander un entraînement de rattrapage **non bloquant**, sous réserve du verrou global d'entraînement.
7. Sinon, ne pas déclencher de rattrapage ; attendre le prochain entraînement à 01:00.
8. Si MLflow est indisponible : garder le service opérationnel autant que possible, charger le cache local du champion si disponible, signaler l'indisponibilité et reprendre la vérification après retour du service. Ne pas lancer plusieurs jobs de rattrapage pendant une panne.

> Pour les comparaisons, stocker et comparer des timestamps **UTC**, pas des chaînes locales. La condition est **strictement supérieure à 25 h**. La valeur 25 h est une règle de rattrapage, distincte de l'heure fixe 01:00.

### 5.2. Entraînement programmé

- Chaque jour à **01:00** dans le fuseau défini par `TRAINING_TIMEZONE`, déclencher une tentative d'entraînement.
- Si un entraînement est déjà en cours, **ne pas lancer de deuxième job** : journaliser le déclenchement ignoré ou mettre en file d'attente selon la politique existante (ne pas empiler les jobs sans limite).
- Le scheduler doit être **unique** : si plusieurs workers/réplicas EC2 ou conteneurs existent, utiliser un scheduler externe ou un verrou distribué/persistant.
- Après un redéploiement, l'entraînement quotidien reste planifié ; le rattrapage ne doit pas générer une seconde session au même moment.
- Pour le changement d'heure (Europe/Paris), définir explicitement la stratégie de résolution des heures ambiguës/inexistantes : à 01:00 l'heure n'est normalement pas supprimée par le changement d'heure européen, mais des décisions explicites sont utiles si la configuration change.

### 5.3. Exécution de l'entraînement

1. Acquérir un verrou/lease exclusif couvrant **scheduler, rattrapage et déclenchements manuels**.
2. Créer un run MLflow avec des tags : `run_type=training`, `trigger=scheduled|catchup|manual`, `dataset_version`, `code_version`, et un identifiant unique de job.
3. Entraîner le challenger sans interrompre le modèle champion utilisé pour l'inférence.
4. Logger paramètres, métriques, références de dataset, code/configuration et artefacts dans MLflow.
5. Enregistrer le nouveau modèle dans MLflow Model Registry sous `MLFLOW_REGISTERED_MODEL_NAME` ; obtenir son numéro de version.
6. Évaluer le challenger selon les **critères métier existants** (même dataset de validation/test et mêmes métriques que le champion, ou protocole de comparaison documenté). Ne pas inventer un seuil de score.
7. Cas **sans champion** : si le modèle candidat passe toutes les validations, le promouvoir avec l'alias `champion`.
8. Cas **avec champion** : promouvoir le challenger uniquement s'il satisfait la politique de comparaison et les validations. Sinon conserver le champion et tracer la décision.
9. En cas de promotion : charger/tester le nouveau modèle côté FastAPI, puis basculer la version active de façon contrôlée. Garder le précédent champion disponible pour rollback.
10. Marquer l'entraînement comme **réussi** uniquement à l'issue des étapes définies comme succès métier. Documenter précisément ce que signifie `training_success_at` : recommandation, fin réussie de l'entraînement et de l'enregistrement, **même si le challenger n'est pas promu**. Ne pas confondre succès d'entraînement et succès de promotion.
11. Relâcher le verrou même en cas d'échec, tout en journalisant l'erreur. Un échec ne met pas à jour la date du dernier entraînement réussi.

### 5.4. Cohérence de la promotion

- Éviter de pointer l'alias `champion` sur un modèle que FastAPI n'est pas capable de charger.
- Préparer et valider le nouveau modèle en mémoire, puis organiser le basculement entre :
  - l'alias durable du Model Registry ;
  - la version active dans FastAPI ;
  - le cache persistant local.
- En cas d'échec entre ces étapes, garder l'ancienne version active et implémenter une procédure de réconciliation/rollback ; ne jamais laisser les prédictions sans modèle fonctionnel.
- Avec plusieurs processus FastAPI, assurer la propagation/rechargement du modèle sur chacun d'eux : une variable globale Python n'est partagée ni entre workers ni entre conteneurs.

## 6. FastAPI et chargement du champion

- L'API de prédiction conserve un **objet modèle chargé en mémoire** : ne pas contacter MLflow ou S3 à chaque requête.
- Au redémarrage de FastAPI, tenter le chargement du champion depuis le Model Registry **si MLflow est disponible** ; sinon tenter un **cache local persistant**, puis signaler proprement l'absence de modèle si aucun des deux n'est disponible.
- Conserver les fichiers du champion dans un répertoire **versionné** et un manifeste atomique (`model_name`, `version`, `artifact_uri`, `checksum` si possible). Utiliser un volume persistant si FastAPI est conteneurisée.
- Prévoir un mécanisme **interne authentifié** pour recharger ou préparer une nouvelle version du champion, par exemple `POST /internal/models/refresh`, sans l'exposer publiquement.
- Charger et valider le nouveau modèle **avant** de substituer la référence active ; ne pas remplacer un modèle fonctionnel par `None` lors d'un refresh.
- Définir précisément le contrat des entrées/sorties, la signature du modèle et les dépendances pour le format réel utilisé par le projet (Scikit-learn, PyTorch, XGBoost, etc.).
- Rendre visible la version active dans un endpoint interne de statut/healthcheck.

## 7. Pseudocode de l'orchestration

```python
async def on_ml_engine_startup():
    # Ne doit pas empêcher indéfiniment l'API de démarrer.
    await wait_for_mlflow_ready_with_bounded_retries()
    await ensure_champion_loaded_if_available()

    last_success = await get_last_successful_training_utc()
    if last_success is None or utc_now() - last_success > timedelta(hours=25):
        await enqueue_training_if_not_running(trigger="catchup")

    # Le scheduler quotidien à 01:00 est géré indépendamment.


async def daily_training_trigger():
    await enqueue_training_if_not_running(trigger="scheduled")


async def training_job(trigger: str):
    async with exclusive_training_lease():
        result = await train_and_register_challenger(trigger=trigger)
        await record_successful_training(result)
        if await challenger_qualifies(result):
            await promote_and_refresh_serving_model_safely(result)
```

> Pseudocode volontairement simplifié : le stockage de l'état, les retries et la politique de promotion doivent être adaptés au code réel. Éviter toute concurrence entre une décision de rattrapage et l'acquisition d'un verrou : rendre la mise en file d'attente/idempotence atomique.

## 8. Cas limites indispensables

| Situation | Comportement attendu |
|---|---|
| Premier déploiement, aucun modèle | Entraînement initial ; promotion du premier candidat valide ; avant cela FastAPI répond proprement que le modèle n'est pas disponible. |
| Dernier succès il y a 24 h | Aucun rattrapage au démarrage ; entraînement prévu à 01:00. |
| Dernier succès il y a exactement 25 h | Aucun rattrapage (seuil **strictement > 25 h**). |
| Dernier succès il y a 26 h | Un entraînement de rattrapage est demandé. |
| Dernière tentative échouée il y a 30 min ; dernier succès il y a 27 h | Le rattrapage reste nécessaire ; prévoir anti-boucle/backoff pour éviter des tentatives infinies après chaque crash. |
| `ml-engine` redémarre pendant un entraînement | Ne pas démarrer une deuxième session sans récupération/expiration contrôlée du verrou ; état du job réconcilié. |
| Redéploiement à 00:59, job de 01:00 imminent | Éviter deux entraînements concurrents ; documenter la stratégie de déduplication. |
| MLflow indisponible au démarrage | Health dégradée et retries ; FastAPI conserve son champion déjà chargé ou son cache ; pas de perte des artefacts. |
| S3 indisponible pendant l'enregistrement | Run en échec ou à finaliser ; **aucune promotion** d'un artefact inaccessible. |
| Challenger moins bon | Champion conservé, challenger historisé. |
| Nouveau champion impossible à charger | Ancien champion conservé ; rollback/réconciliation de l'alias et de la version active. |
| Plusieurs workers FastAPI | Chargement et basculement cohérents par worker, sans hypothèse de RAM partagée. |
| Redémarrage EC2 complet | MLflow et stockage persistant redémarrent ; champion restauré ; contrôle des 25 h effectué. |

## 9. Tests demandés

- Tests unitaires : calcul du seuil de 25 heures, absence d'historique, timestamps UTC, distinction run réussi/échoué, logique de promotion, verrouillage et idempotence.
- Tests d'intégration MLflow : création de run, logging d'artefacts, enregistrement d'une version, lecture/écriture de l'alias `champion`, rechargement du modèle.
- Tests S3 : artefact réellement accessible dans le bucket et sous le préfixe configuré (en environnement de test, ou avec mocks adaptés).
- Tests FastAPI : prédictions continues pendant entraînement, chargement initial, remplacement atomique, rollback en échec, cache après redémarrage, absence de champion.
- Tests scheduler : déclenchement à 01:00, interaction avec rattrapage, redémarrages, DST/fuseau, et absence de doublon.
- Tests de panne : MLflow indisponible, S3 indisponible, crash en cours de training, cache manquant, multiples processus.

## 10. Livrables attendus de l'IA de développement

1. **Audit du dépôt existant** : composants/services actuels, MLflow, branchement S3, framework des modèles, backend SQL, mécanisme d'ordonnancement, façon de déployer, processus FastAPI.
2. **Plan de modifications fichier par fichier** : ce qui sera ajouté, modifié ou réutilisé, en conservant les conventions du projet.
3. **Implémentation** avec code complet des parties concernées, configuration MLflow, paramètres d'environnement, permissions IAM à prévoir, orchestration des entraînements, alias `champion`, chargement FastAPI et cache.
4. **Migrations** éventuelles de la base MLflow et des artefacts, sans perte des expériences existantes ; indiquer celles nécessitant une intervention manuelle.
5. **Tests automatisés** couvrant les cas ci-dessus.
6. **Documentation d'exploitation** : première installation, démarrage, redéploiement, vérification du modèle actif, rattrapage, logs, dépannage, rollback et commandes de diagnostic.
7. **Estimation des coûts supplémentaires AWS** en fonction de la région, du stockage supplémentaire S3, des requêtes/transferts, des volumes EBS, du backend SQL choisi et des services réellement utilisés. Réutiliser l'EC2 et le S3 existants autant que possible ; ne pas supposer que le Registry MLflow impose SageMaker.

## 11. Critères d'acceptation

- [ ] MLflow démarre automatiquement avec l'application et **reste actif**.
- [ ] MLflow utilise un backend de métadonnées persistant et le **bucket S3 existant** pour les artefacts.
- [ ] Les modèles entraînés sont enregistrés et versionnés dans le **MLflow Model Registry**.
- [ ] Le champion est identifiable via `models:/<NOM_DU_MODELE>@champion`.
- [ ] `ml-engine` sait récupérer, comparer et promouvoir le champion, sans interrompre les prédictions en cours.
- [ ] En l'absence de champion, un premier modèle valide peut être créé et promu.
- [ ] Entraînement planifié à **01:00 chaque jour**, dans un fuseau explicitement configuré.
- [ ] Au démarrage/re-déploiement, contrôle de MLflow puis contrôle du dernier entraînement **réussi** ; rattrapage si **> 25 h** ou absent.
- [ ] Aucun entraînement simultané ni doublon entre rattrapage, planification et redéploiement.
- [ ] FastAPI continue de prédire à partir du champion en mémoire pendant l'entraînement.
- [ ] FastAPI sait restaurer le champion après un redémarrage et exposer sa version active.
- [ ] Erreurs et interruptions gérées avec logs, retry/backoff, cache et rollback appropriés.
- [ ] Tests automatisés et documentation de déploiement fournis.

## 12. Instructions finales à l'IA

**Commencer par examiner l'architecture réelle du dépôt.** Ne pas créer un second `ml-engine`, ne pas introduire SageMaker ni un registry maison, ne pas remplacer les outils d'ordonnancement existants sans justification. Réutiliser les composants, conventions, APIs et modèles de données déjà présents.

S'il reste des détails inconnus (nom du modèle, framework, règles de promotion, région AWS, modèle d'exécution FastAPI, Docker Compose, base existante), **les repérer explicitement** et proposer des valeurs configurables, plutôt que de considérer des exemples de ce document comme des faits.

Présenter d'abord une synthèse de l'architecture et un plan d'implémentation concret ; puis produire les modifications de code avec tests et documentation.
