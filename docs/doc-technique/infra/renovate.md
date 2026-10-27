# Renovate

Renovate est un outil qui automatise la mise à jour des dépendances de notre projet.

## Configuration

Sa configuration se trouve à la racine du projet, dans le fichier `renovate.json5`.

```json5 title="renovate.json"
{
  // Autorisé à créer des PR entre minuit et 6h
  "schedule": ["before 6am"],
  "timezone": "Europe/Paris",

  // Attend 3 jours après la publication d'une version
  "minimumReleaseAge": "3 days",

  // 5 PR Renovate ouvertes simultanément au maximum
  "prConcurrentLimit": 5,

  "vulnerabilityAlerts": {
    // Les correctifs de sécurité ignorent la planification
    "schedule": ["at any time"]
  }
}
```

!!! note
    Les alertes de sécurité ne sont prises en compte que si les Dependabot alerts sont activées sur le dépôt GitHub.

## Fonctionnement de Renovate

Sur GitHub, dans l'onglet **Issues**, on trouve une issue nommée « Dependency Dashboard ».

Voici comment interpréter ses principales sections :

- **Pending Approval** : mises à jour qui attendent une validation manuelle avant la création de la PR (selon la configuration, par exemple pour les versions majeures).
- **Awaiting Schedule** : mises à jour détectées, mais dont la PR n'est pas encore créée, car Renovate attend la fenêtre de planification définie.
- **Pending Status Checks** : mises à jour dont la PR n'est pas encore créée, car des vérifications de statut sont en attente (CI, ou âge minimum de la release non atteint).

Chaque section contient des cases à cocher. Cocher une case demande à Renovate de créer la PR immédiatement, en ignorant la règle qui la bloquait.

## Comment reconnaître une PR Renovate ?

Elle se reconnaît à deux éléments :

- sa branche, dont le nom commence par `renovate/` ;
- son auteur, noté `renovate[bot]`.