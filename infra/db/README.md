# Comptes PostgreSQL

La base applicative est partagée, mais chaque service utilise un compte distinct.
Les rôles SQL n'ont aucun lien avec les rôles métier `USER` et `ADMIN` de l'API.

| Compte | Accès |
| --- | --- |
| `core_api` | Lecture des tables exposées par l'API ; insertion et mise à jour de `users` |
| `etl_worker` | Lecture/insertion/mise à jour des sites, profils et mesures ; insertion des alertes et lecture de leur identifiant pour déduplication |
| `prediction_jobs` | Lecture des sites, profils et mesures horaires ; lecture/insertion/mise à jour des jobs ; lecture/insertion des lots et prévisions |
| `monitoring` | `pg_monitor`, sans lecture des données métier |
| `enervision_migrator` | Peut prendre `enervision_owner`, sans administration des rôles ou du serveur |
| `enervision_owner` | Propriétaire des objets applicatifs, sans connexion (`NOLOGIN`) |

`prediction-service` (HTTP) n'a pas de connexion SQL. `scheduler` et les commandes
manuelles de l'ETL partagent le compte `etl_worker`, puisqu'ils exécutent les mêmes
opérations. MLflow conserve son compte et sa base séparés.

## Ordre d'exécution

1. `db` démarre avec le superutilisateur historique défini par `POSTGRES_USER`.
2. `db-bootstrap` utilise ce superutilisateur pour installer TimescaleDB, créer ou
   réconcilier les comptes et mots de passe, et transférer les tables applicatives
   existantes au propriétaire sans connexion. Il ne transfère pas les catalogues
   de l'extension. Cette étape s'exécute aussi sur les volumes existants.
3. `migrate` se connecte comme `enervision_migrator` avec l'option JDBC
   `options=-c%20role%3Denervision_owner`. Les objets, y compris les tables Liquibase,
   appartiennent ainsi à `enervision_owner` dès leur création.
4. Le changeset `009` réapplique la matrice des droits à chaque migration.
5. Les services démarrent après une migration réussie.

Le déploiement exécute explicitement le bootstrap et les migrations, même pour une
release ne sélectionnant que `db`. Les erreurs empêchent l'activation de la release.
Une release applicative seule ne recrée pas le conteneur PostgreSQL ; sa recréation
nécessite que `db` soit explicitement sélectionné.
L'ancien fichier `007` reste inchangé mais n'est plus inclus dans le changelog actif :
la gestion du compte monitoring est assurée par le bootstrap administrateur. Les
entrées déjà présentes dans `databasechangelog` sont conservées.

## Première activation

En local, renseigner les nouveaux secrets de `.env.example` et les deux URL avec
les mots de passe correspondants. Pour les URL, utiliser des secrets hexadécimaux
(`openssl rand -hex 24`) ou encoder les caractères réservés. Pour l'API lancée sur
l'hôte, renseigner également `SPRING_DATASOURCE_PASSWORD` avec le secret `core_api`.
Ne jamais remplacer `POSTGRES_USER` sur un volume existant pour créer un compte.

En production, appliquer d'abord les changements Terraform : quatre secrets de
comptes et deux URL dédiées sont écrits dans SSM. Le déploiement applicatif doit
ensuite recréer **core-api, scheduler et prediction-jobs**, afin qu'aucun ancien
conteneur ne continue à utiliser le superutilisateur. Les fichiers Compose modifiés
sélectionnent tous les services via `.github/services.json`.

Effectuer une sauvegarde vérifiée avant la première activation. Les sauvegardes
existantes exportent les rôles (`pg_dumpall --globals-only`) et les propriétaires ;
les restaurer avant les données. Ne pas utiliser `REASSIGN OWNED` sur le compte
administrateur : cela pourrait affecter les objets d'extension et d'autres bases.

## Secrets et rotation

Les secrets administrateur sont réservés à `db`, `db-bootstrap` et `mlflow-init`.
L'ETL reçoit une liste explicite de variables ; le `.env` complet n'est jamais
injecté dans ses conteneurs. Le fichier hôte reste privé (`umask 077` au déploiement).
La séparation SQL ne protège pas contre un administrateur Docker ou un processus
qui peut récupérer les secrets SSM via les droits de l'hôte EC2.

Une rotation nécessite de changer le secret SSM **et** l'URL associée pour l'ETL ou
les jobs, exécuter le bootstrap, puis recréer les services concernés. Coordonner ces
opérations : les connexions existantes ne sont pas invalidées par `ALTER ROLE`,
mais les nouvelles connexions utilisant l'ancien secret échoueront. En local,
exécuter `docker compose run --rm db-bootstrap`, puis `docker compose up -d` avec
les services concernés. Ne pas compter sur le seul redémarrage de `db`.

Après vérification des connexions applicatives (`pg_stat_activity`, identités et
`application_name`), renouveler également le secret administrateur historique
qui était auparavant partagé. Mettre à jour PostgreSQL et SSM de façon coordonnée :
modifier `POSTGRES_PASSWORD` dans Compose seul ne change pas une base existante.
Un retour à une ancienne release réutilisant le compte administrateur doit rester
une opération exceptionnelle ; les migrations et secrets ne sont pas annulés par
le retour arrière des images.

## Maintenance et vérification

- Toute nouvelle table doit avoir ses `GRANT` explicites dans sa migration.
  Aucun droit global n'est accordé automatiquement aux futurs objets de `public`.
- Aucun service applicatif n'est propriétaire des tables ni membre du rôle propriétaire.
- Pas de `DELETE`, `TRUNCATE`, `CREATEDB`, `CREATEROLE`, réplication ou contournement RLS.
- `PUBLIC` ne peut ni créer dans le schéma `public` ni se connecter à la base
  applicative ; `mlflow-init` retire également l'accès public à la base MLflow.
- Ne jamais afficher `docker compose config` avec les vrais secrets dans les logs.
- Adapter les pools et délais aux ressources disponibles et aux durées des jobs ;
  les comptes séparés permettent de suivre les connexions par service.

Tests isolés, sans accès à la base de développement ou de production :

```sh
python3 -m unittest discover -s infra/db/tests -v
# Pour vérifier la version actuellement en service :
TIMESCALE_TEST_IMAGE=timescale/timescaledb:2.17.2-pg16 python3 -m unittest discover -s infra/db/tests -v
```

Ces tests démarrent un conteneur TimescaleDB jetable sans réseau externe et
exécutent Liquibase avec son vrai compte limité. Ils vérifient les opérations des
services, les refus d'accès, les nouveaux chunks, une migration depuis l'ancien
changelog, les répétitions et la rotation des secrets. Ils valident aussi les
configurations Compose locale et production avec des secrets de test uniquement.
La CI teste `2.17.2-pg16` et `2.30.2-pg16` séparément. L'image de test par défaut
est celle épinglée dans Compose (`2.30.2-pg16`).
