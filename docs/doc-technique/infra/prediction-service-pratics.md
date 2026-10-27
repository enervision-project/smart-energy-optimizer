# Données, suivi quotidien et nouveaux champions

!!! info "Cycle recommandé pour la suite du projet"
    Cette page décrit la méthode à mettre en place. Le [fonctionnement actuel du service](prediction-service.md) décrit ce qui est déjà codé. Les changements ci-dessous ne sont pas automatiquement implémentés par cette documentation.

Pour l'instant, le cycle utilise uniquement les trois Parquet historiques : Train pour l'apprentissage, Validation pour son évaluation séparée et `test.parquet` pour le test final et la comparaison champion/challenger. L'ajout de données récentes et d'un second Test décrit ci-dessous reste une évolution future.

Le cycle proposé est simple : **surveiller chaque jour, accumuler des données propres, préparer de nouveaux Parquet, entraîner des challengers, puis remplacer le champion seulement après une comparaison favorable sur des données réservées.**

## 1. Surveiller le champion chaque jour

Comparer ses prévisions enregistrées aux consommations réelles de `readings_hours`, une fois les heures stabilisées. L'ETL pouvant corriger les six dernières heures, le calcul doit laisser passer cette fenêtre de correction et le passage d'agrégation.

Suivre quotidiennement trois éléments :

- **Qualité des données** : heures manquantes, consommations nulles et sites insuffisamment renseignés.
- **Drift** : changement des données par rapport à une période de référence saine, en tenant compte de la saison et des jours ouvrés.
- **Erreur du champion** : NMAE macro et résultats par site sur les consommations réellement observées.

Le drift est un signal d'évolution. Il ne déclenche pas à lui seul le remplacement du modèle. Une hausse durable des erreurs sur des données propres peut justifier un nouvel entraînement. La distinction entre suivi des données et suivi des performances est décrite dans les [recommandations de surveillance de Google](https://developers.google.com/machine-learning/managing-ml-projects/production).

!!! warning "Avec le recalage de niveau, suivre deux erreurs et le ratio"
    Les prévisions publiées sont recalées par un ratio mesuré / prévu de chaque site (voir [Recalage de niveau](prediction-service.md#recalage-de-niveau)). Ce recalage corrige l'échelle : l'erreur publiée (`prediction_kwh`) reste donc bonne même quand les données dérivent. Pour ne pas masquer la dérive, suivre séparément :

    - l'**erreur du champion seul**, à partir de `model_prediction_kwh` : c'est elle qui justifie un réentraînement ;
    - l'**erreur publiée**, à partir de `prediction_kwh` : c'est la qualité vue par l'utilisateur ;
    - le **ratio** `level_ratio` de chaque site : durablement loin de 1, il mesure la dérive de niveau ; un saut brutal signale un changement récent ou un problème de collecte ; un ratio aux bornes (0,5 ou 1,5) signifie que la correction ne suffit plus.

    Un challenger entraîné sur les données récentes devra battre le **champion recalé**, et non le champion brut.

    Ces trois indicateurs sont déjà suivis heure par heure : `prediction-jobs` les écrit dans ses logs après chaque série (`monitoring.py`), et Grafana les affiche dans la ligne « Modèle (prévisions) » du dashboard (voir [Monitoring](monitoring.md)).

## 2. Accumuler des données propres sur plusieurs semaines

Les nouvelles heures restent collectées par l'ETL. On attend d'avoir assez de recul pour couvrir plusieurs cycles de travail et disposer de périodes distinctes pour apprendre et comparer les modèles.

Le nombre de lignes ne suffit pas : il faut vérifier la durée couverte, la qualité et la présence de chaque site. Une semaine complète ne représente qu'un cycle hebdomadaire ; elle ne couvre pas toute la saisonnalité.

Une fois ces conditions remplies, exporter un **nouveau dataset Parquet versionné** sur S3. Conserver les anciens fichiers, les dates des nouvelles périodes et les règles de préparation pour pouvoir reproduire l'expérience.

## 3. Préparer de nouveaux jeux Train, Validation et Test

Pour une future génération, le Train historique et la Validation historique pourront être combinés une fois les hyperparamètres fixés, puis complétés avec une partie des nouvelles données. **Le Test historique reste conservé à part et ne rejoint jamais le Train.**

Réserver également une période récente pour créer un second Test :

| Nouveau jeu | Données | Utilisation |
| --- | --- | --- |
| Train | Train + Validation historiques, après fixation des hyperparamètres, et partie ancienne des nouvelles données propres | Entraîner le challenger. |
| Validation | Période SQL suivante, absente du train | Choisir les hyperparamètres si plusieurs configurations sont essayées. |
| Test historique | `test.parquet` d'origine, conservé à part | Vérifier les performances sur le contexte historique. |
| Test récent | Période SQL la plus récente, conservée à part | Comparer le challenger retenu au champion sur le contexte actuel. |

```text
Passé                                                        Récent
[ Historique + nouvelles données Train ][ Validation ][ Test réservé ]
Le Test historique reste séparé de ces nouvelles données.
```

Les dates de coupure sont communes aux sites. Le Test doit être absent de l'entraînement des deux modèles. Si le champion a déjà appris cette période, il faut en choisir une plus récente. Les prétraitements s'apprennent uniquement sur le Train. Voir les [précautions scikit-learn contre les fuites de données](https://scikit-learn.org/stable/common_pitfalls.html).

Les scores du Test historique et du Test récent sont publiés séparément pour ne pas masquer une dégradation récente dans une moyenne globale.

## 4. Entraîner puis comparer les challengers

Commencer avec le même HGB et les mêmes hyperparamètres pour mesurer l'effet des nouvelles données. Le challenger est un nouveau modèle ajusté sur le nouveau Train ; le champion continue de produire les prévisions pendant ce calcul.

Si plusieurs configurations sont essayées, choisir le candidat sur la Validation. Comparer ensuite ce candidat au champion sur **les mêmes sites et les mêmes heures de chaque Test**, avec la même règle de qualité des consommations. Pour l'instant, seul le Test historique est utilisé ; le second Test sera ajouté ultérieurement.

Éviter de consulter le Test après chaque réglage : il finirait par guider les choix et perdrait son indépendance. Si on relance une campagne après un échec, conserver le résultat et prévoir une nouvelle période réservée pour la confirmation.

## 5. Changer de champion seulement avec un gain supérieur à 4 %

Le critère principal reste la **NMAE macro**, moyenne des NMAE calculées par site. Plus elle est faible, meilleure est la prévision sur le jeu évalué.

```text
gain relatif (%) = 100 × (score champion − score challenger) / score champion
```

Exemple, avec un champion à 12,9 % sur le Test utilisé pour la promotion :

| Score du challenger sur le même Test | Gain relatif | Décision proposée |
| --- | --- | --- |
| 12,5 % | Environ 3,1 % | Garder le champion. |
| 12,1 % | Environ 6,2 % | Promotion possible après contrôle des résultats par site. |

La règle proposée ici demande **plus de 4 % de gain relatif**, avec un score champion positif et défini. Vérifier aussi que le gain est représentatif et qu'il ne masque pas une forte dégradation sur un site important. Le seuil actuellement codé accepte exactement 4 % ; rendre la règle strictement supérieure demanderait une modification du code.

Actuellement, cette comparaison porte sur le Test historique. Lorsque le Test récent sera disponible, le gain sera évalué sur ce dernier, avec un contrôle séparé des régressions sur le Test historique.

La décision ne consiste pas à choisir celui qui a « le moins de drift ». Le drift sert à comprendre les évolutions ; la comparaison des erreurs sur le Test réservé permet de vérifier si le challenger prévoit mieux.

Après promotion, conserver la version précédente, tracer les données et les scores utilisés pour la décision, puis poursuivre le suivi quotidien du nouveau champion sur les heures futures.
