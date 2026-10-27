# Documentation du Workflow CI

Ce document décrit le fonctionnement du pipeline d'Intégration Continue (CI) principal du projet. Conçu pour une architecture monorepo, il optimise les temps d'exécution en déclenchant uniquement les processus liés aux composants modifiés.

## Déclencheurs (Triggers)

Le workflow s'exécute dans les contextes suivants :

* **Pull Request** : À chaque création ou mise à jour d'une PR, pour valider les changements.
* **Push sur `main`** : Après la fusion d'une PR.
* **Déclenchement manuel** (`workflow_dispatch`) : Permet de lancer le pipeline à la demande depuis l'interface GitHub.

!!! info "Gestion de la concurrence"
    Sur les Pull Requests, tout nouveau push annule l'exécution en cours du workflow précédent afin d'économiser les ressources. Les exécutions sur la branche `main` vont toujours jusqu'à leur terme.

## Structure du Workflow

Le workflow est divisé en deux grandes phases : la détection des changements et l'exécution sélective des jobs enfants.

### 1. Détection des modifications (`changes`)

Ce job analyse les fichiers modifiés et détermine quels composants nécessitent d'être testés.

* **Filtres par chemins (`dorny/paths-filter`)** :
    * Frontend
    * Core API
    * Terraform
    * ETL Worker

* **Filtres d'images (`../../../scripts/ci/changed-services.py`)** : Uniquement sur les PR, un script Python vérifie quels services nécessitent un build d'image Docker en se basant sur la branche de base de la PR.

### 2. Exécution des sous-workflows

Chaque composant dispose de son propre workflow réutilisable appelé conditionnellement si des changements ont été détectés, ou si le workflow est lancé manuellement.

| Composant | Job | Workflow appelé | Prérequis / Secrets |
| :--- | :--- | :--- | :--- |
| **Frontend** | `call-frontend` | `_ci-frontend.yml` | `SONAR_TOKEN_FRONTEND` |
| **Core API** | `call-core-api` | `_ci-core-api.yml` | `SONAR_TOKEN_CORE_API` |
| **ETL Worker**| `call-etl-worker` | `_ci-etl-worker.yml` | `SONAR_TOKEN_ETL_WORKER` |
| **Terraform** | `call-terraform` | `_ci-terraform.yml` | Permissions `id-token: write`. Identifiants `ENERGY_API_USERNAME` / `PASSWORD`. |
| **Docker Images**| `call-images` | `_ci-images.yml` | S'exécute uniquement sur les PR avec la liste des images fournie par le job de détection. |

### 3. Validation finale pour la fusion (`mr-ok`)

Dans un monorepo, les statuts GitHub requis pour fusionner une Pull Request peuvent être complexes à configurer car tous les jobs ne tournent pas systématiquement (ils sont "skipped" si non modifiés).

Le job `mr-ok` résout ce problème. Il dépend de **tous** les autres jobs et consolide leurs résultats.

!!! success "Critères de réussite"
    * Il s'assure qu'aucun sous-job n'a échoué ou n'a été annulé.
    * Il réussit uniquement si tous les jobs dépendants ont le statut `success` ou `skipped`.

!!! tip "Configuration GitHub"
    C'est **un des check** (*status check*) qui est marqué comme obligatoire dans les règles de protection de branche (rulesets) de GitHub pour autoriser la fusion d'une Pull Request.