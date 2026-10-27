# Sauvegardes et protection des données

## Objectif

Pouvoir récupérer les données après une suppression, une panne ou une corruption.
La cible est une sauvegarde quotidienne chiffrée, conservée dans un bucket S3 privé
avec Object Lock pour empêcher sa suppression pendant la période de rétention.

Le périmètre couvre les bases TimescaleDB et MLflow, le datalake S3,
les fichiers de déploiement, l’état Terraform, les paramètres SSM nécessaires à la
reprise et les logs système, Docker et Loki des deux instances.

## Rétention

**Pour le MVP, nous visons 7 jours de rétention des sauvegardes et des archives de
logs**, afin de limiter les coûts et de démontrer le fonctionnement.

| Données | MVP | Cible pour une exploitation durable |
| --- | --- | --- |
| Sauvegardes BDD, S3 et configuration | 7 jours | 30 jours de sauvegardes quotidiennes, à adapter aux besoins de reprise |
| Archives de logs de sécurité et d’accès | 7 jours | 6 mois à 1 an, selon la recommandation CNIL et les exigences applicables |
| Logs techniques consultables dans Loki | 7 jours | 7 à 30 jours selon les besoins de dépannage, avec archives de sécurité séparées |

Les 30 jours constituent un choix opérationnel, pas une obligation légale générale.
La recommandation de 6 mois à 1 an concerne les traces de sécurité et d’accès aux
données personnelles ; les durées doivent être justifiées selon l’activité.
L’expiration S3 est demandée à J+7 pour le MVP, mais la suppression effective des
versions est asynchrone et peut intervenir plus tard.

## Vérification de l’intégrité

Un contrôle accompagne chaque sauvegarde : comparaison des empreintes SHA-256,
lecture des archives de logs et restauration des bases dans un environnement isolé.
La lecture des tables et la vérification des structures prises en charge avec
`pg_amcheck` permettent de détecter des problèmes supplémentaires.

Une sauvegarde quotidienne vise une perte de données d’environ 24 heures au maximum
lorsque toutes les exécutions réussissent. Le temps de remise en service doit être
mesuré par un exercice de restauration. Ces contrôles ne garantissent pas l’absence
d’une erreur métier déjà présente dans les données sources.

## Renforcement après le MVP

- Conserver une copie dans un autre compte AWS et, si nécessaire, une autre région.
- Archiver les journaux PostgreSQL (WAL) pour restaurer à un instant précis.
- Collecter les traces de sécurité en continu et alerter sur les sauvegardes absentes
  ou les restaurations échouées.

## Références

- [CNIL : journalisation et durées recommandées](https://www.cnil.fr/fr/securite-tracer-les-operations)
