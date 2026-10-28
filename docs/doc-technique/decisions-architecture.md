# Décisions d'architecture (ADR)

Chaque décision suit le même format : **contexte**, **décision**, **pourquoi**, **conséquences**. Une décision remise en cause n'est pas effacée : on ajoute une nouvelle ADR qui la remplace.

| N° | Décision | Domaine |
|---|---|---|
| [001](#adr-001-monolithe-modulaire-pour-core-api) | Monolithe modulaire pour core-api | Back |
| [002](#adr-002-une-seule-base-postgresql-timescaledb) | Une seule base PostgreSQL + TimescaleDB | Données |
| [003](#adr-003-les-services-communiquent-par-la-base) | Les services communiquent par la base | Architecture |
| [004](#adr-004-etl-planifie-par-cron) | ETL planifié par cron | Données |
| [005](#adr-005-donnees-brutes-archivees-dans-s3-avant-la-base) | Données brutes archivées dans S3 avant la base | Données |
| [006](#adr-006-ne-jamais-ecraser-une-valeur-brute) | Ne jamais écraser une valeur brute | Données |
| [007](#adr-007-jwt-sans-etat-emis-par-core-api) | JWT sans état émis par core-api | Sécurité |
| [008](#adr-008-interrogation-toutes-les-30-s-plutot-que-du-temps-reel) | Interrogation toutes les 30 s plutôt que du temps réel | Front |
| [009](#adr-009-previsions-precalculees-chaque-heure) | Prévisions précalculées chaque heure | ML |
| [010](#adr-010-modele-global-calendaire-sans-meteo-ni-lags) | Modèle global calendaire, sans météo ni lags | ML |
| [011](#adr-011-promotion-automatique-champion-challenger) | Promotion automatique champion / challenger | ML |
| [012](#adr-012-une-ec2-et-docker-compose-plutot-quun-orchestrateur) | Une EC2 et Docker Compose plutôt qu'un orchestrateur | Infra |
| [013](#adr-013-caddy-comme-unique-point-dentree) | Caddy comme unique point d'entrée | Infra |
| [014](#adr-014-monitoring-sur-une-ec2-dediee) | Monitoring sur une EC2 dédiée | Infra |

---

## ADR-001 : Monolithe modulaire pour core-api

- **Contexte** : l'API couvre quatre domaines (comptes, sites, alertes et recommandations, mesures et prévisions), développés par une petite équipe.
- **Décision** : un seul processus Spring Boot, découpé en modules Maven (`user`, `configuration`, `diagnostic`, `telemetry`, `common`, `bootstrap`).
- **Pourquoi** : les frontières entre domaines sont nettes dans le code, sans le coût des microservices (réseau, déploiements multiples, transactions distribuées).
- **Conséquences** : un module peut être extrait plus tard en service. Une dépendance entre modules doit être déclarée dans le `pom.xml` ; elle reste visible.

## ADR-002 : Une seule base PostgreSQL + TimescaleDB

- **Contexte** : des séries temporelles à la minute, plus des données relationnelles (sites, comptes, droits).
- **Décision** : PostgreSQL 16 avec l'extension TimescaleDB. `readings_raws` est une hypertable découpée en blocs de 7 jours. Schéma géré par Liquibase.
- **Pourquoi** : une seule base à opérer, du SQL standard pour tout, et des performances de base de séries temporelles là où il le faut.
- **Conséquences** : le partitionnement par date est déjà en place pour monter en volume. Tout changement de schéma passe par un nouveau changeset.

## ADR-003 : Les services communiquent par la base

- **Contexte** : ETL, ML et API tournent à des rythmes différents (minute, heure, à la demande).
- **Décision** : pas d'appel direct entre services. Chaque table a un seul écrivain ; les autres la lisent.
- **Pourquoi** : un service arrêté ne bloque pas les autres. core-api continue de répondre si l'ETL ou le ML tombe, avec les dernières données disponibles.
- **Conséquences** : la base est le contrat entre services. Un changement de colonne concerne tous ses lecteurs.

## ADR-004 : ETL planifié par cron

- **Contexte** : sept sites à interroger chaque minute, plus un rattrapage et des agrégats horaires.
- **Décision** : un conteneur `scheduler` avec cron. Un verrou `flock` par tâche empêche deux exécutions simultanées.
- **Pourquoi** : le besoin est simple et régulier. Un orchestrateur (Airflow) ou une file de messages serait surdimensionné.
- **Conséquences** : une seule instance possible, le verrou étant local au conteneur. Pour monter en charge : paralléliser les appels, puis répartir les sites entre instances ou passer à une file de tâches.

## ADR-005 : Données brutes archivées dans S3 avant la base

- **Contexte** : l'API Mock recalcule son historique à chaque appel ; une réponse perdue ne se retrouve pas à l'identique.
- **Décision** : chaque réponse est écrite telle quelle en JSON Lines dans S3 (couche bronze), **avant** l'écriture en base.
- **Pourquoi** : on peut toujours rejouer ou auditer une collecte, même si la base échoue ou si une transformation était fausse.
- **Conséquences** : un échec d'écriture S3 arrête la tâche. En local, sans bucket, rien n'est archivé.

## ADR-006 : Ne jamais écraser une valeur brute

- **Contexte** : les capteurs renvoient régulièrement des NULL, et le sujet impose de ne pas les masquer.
- **Décision** : les valeurs sont stockées telles que reçues. Une consommation imputée va dans une colonne à part (`consumption_kw_imputed`) avec sa méthode. Une minute rattrapée est marquée `source = 'backfill'`.
- **Pourquoi** : la fiabilité des capteurs reste mesurable, et chaque valeur affichée est traçable.
- **Conséquences** : les agrégats et le ML n'utilisent que les valeurs brutes. Le front distingue mesuré et estimé.

## ADR-007 : JWT sans état émis par core-api

- **Contexte** : authentifier le front, avec deux rôles et des droits par site.
- **Décision** : core-api émet un JWT signé en HS256, valable 1 h, sans jeton de renouvellement. Le front le garde en `sessionStorage`. Les droits par site sont vérifiés dans chaque module via `SiteService` ; un site non visible répond 404.
- **Pourquoi** : pas de session serveur ni de service d'identité à opérer, et chaque instance de core-api peut vérifier un jeton seule.
- **Conséquences** : un changement de rôle ne s'applique qu'au jeton suivant, et un jeton ne peut pas être révoqué avant son expiration.

## ADR-008 : Interrogation toutes les 30 s plutôt que du temps réel

- **Contexte** : afficher les nouvelles alertes sans recharger la page.
- **Décision** : le front relit l'API toutes les 30 s. Pas de SSE ni de WebSocket.
- **Pourquoi** : l'ETL ne collecte qu'une fois par minute, donc le temps réel n'apporterait rien. Il compliquerait le proxy, l'authentification JWT et les tests.
- **Conséquences** : jusqu'à 30 s de retard d'affichage, et une charge d'API proportionnelle au nombre d'onglets ouverts.

## ADR-009 : Prévisions précalculées chaque heure

- **Contexte** : afficher 24 h de prévisions par site.
- **Décision** : `prediction-jobs` complète chaque heure la fenêtre des 24 h suivantes dans `predictions` : seules les heures manquantes sont calculées (en temps normal H+24 ; les 24 au démarrage, après un échec ou un changement de champion). core-api lit, pour chaque heure, la prévision du dernier lot complet ; il n'appelle jamais `prediction-service`.
- **Pourquoi** : la page reste rapide et disponible même si le modèle ou MLflow est en panne, et chaque prévision publiée est historisée.
- **Conséquences** : une heure garde le ratio de recalage du moment où elle a été prévue (en général 24 h avant), écart négligeable car les ratios sont stables. Environ 170 lignes par jour au lieu de 4 000.

## ADR-010 : Modèle global calendaire, sans météo ni lags

- **Contexte** : prévoir la consommation horaire des sept sites à partir d'un historique CSV.
- **Décision** : un seul modèle HistGradientBoosting pour tous les sites, avec cinq variables : `site_id`, `hour`, `day_of_week`, `month`, `is_working_hours`.
- **Pourquoi** : la température ne sera pas connue pour les heures à prévoir. Les lags n'améliorent pas le score (12,92 % de nMAE sans lags contre 13,08 à 13,33 % avec, campagne de 96 essais).
- **Conséquences** : le modèle ne suit pas les changements de niveau des données réelles. Un recalage par site (ratio mesuré / prévu sur 7 jours) corrige l'échelle avant publication.

## ADR-011 : Promotion automatique champion / challenger

- **Contexte** : réentraîner régulièrement sans dégrader la prévision publiée.
- **Décision** : chaque nuit, un challenger est entraîné et comparé au champion sur les mêmes lignes de `test.parquet`. Il le remplace si sa nMAE est au moins 4 % meilleure. Le registre MLflow porte l'alias `champion`.
- **Pourquoi** : la marge de 4 % évite de changer de modèle pour un écart dû au hasard. Tout est tracé dans MLflow.
- **Conséquences** : un entraînement réussi peut se terminer sans promotion. Le champion en place continue de servir pendant l'entraînement et en cas d'échec. Tant que l'entraînement lit les mêmes Parquet (graine fixe), le challenger est identique au champion et n'est jamais promu : l'entraînement nocturne vérifie la chaîne de bout en bout. Le passage aux données de prod est reporté faute de recul (voir [Données, suivi quotidien et nouveaux champions](infra/prediction-service-pratics.md)).

## ADR-012 : Une EC2 et Docker Compose plutôt qu'un orchestrateur

- **Contexte** : déployer une dizaine de conteneurs pour un projet au volume modeste, avec un budget limité.
- **Décision** : une EC2 (`t3.small`) qui exécute `compose.yaml` + `compose.prod.yaml`. Images construites par GitHub Actions, poussées dans ECR, déployées par SSM Run Command (pas de SSH). Infrastructure décrite en Terraform.
- **Pourquoi** : coût d'environ 25 $/mois, et le même fichier Compose en local et en production. Kubernetes ou ECS ajouteraient un coût et une complexité sans besoin réel à ce volume.
- **Conséquences** : pas de haute disponibilité : si l'EC2 tombe, l'application est indisponible. La mémoire est partagée entre tous les services (limites `mem_limit` par conteneur).

## ADR-013 : Caddy comme unique point d'entrée

- **Contexte** : servir le front et l'API en HTTPS.
- **Décision** : Caddy reçoit tout le trafic public. `/api/*` va vers core-api, le reste vers le front, sur le même domaine.
- **Pourquoi** : certificats Let's Encrypt obtenus et renouvelés automatiquement, et pas de CORS puisque front et API partagent le domaine.
- **Conséquences** : les autres services (base, MLflow, prediction-service) ne sont jamais exposés ; on y accède par tunnel SSM.

## ADR-014 : Monitoring sur une EC2 dédiée

- **Contexte** : surveiller les services, la base et le proxy.
- **Décision** : Prometheus, Loki et Grafana sur une EC2 séparée. Sur l'EC2 applicative, Alloy collecte et pousse métriques et logs. Connexion à Grafana par GitHub, réservée aux membres de l'organisation.
- **Pourquoi** : le monitoring ne consomme pas la mémoire de l'EC2 applicative et reste consultable quand elle a un problème.
- **Conséquences** : une deuxième instance à payer et à maintenir.
