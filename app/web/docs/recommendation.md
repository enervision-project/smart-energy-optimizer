# Recommandations énergétiques

Ce composant restitue les recommandations calculées en temps réel par `core-api` pour un site donné, afin d'évaluer la santé électrique et l'efficacité des installations.

---

## 1. Vue d'ensemble

Le panneau de recommandations est affiché sur le tableau de bord de détail d'un site (`/sites/:id`), positionné immédiatement au-dessus des graphiques de consommation horaire.

Pour chaque site sélectionné, l'application analyse et affiche jusqu'à trois indicateurs fondamentaux :

1. **Le facteur de puissance (cos φ)** : optimisation de l'énergie réactive et évitement des pénalités fournisseurs.
2. **La stabilité de tension (V)** : préservation des équipements contre les sous-tensions et surtensions.
3. **Le taux de charge (%)** : marge de sécurité de l'infrastructure électrique et prévention des surcharges.

---

## 2. Restitution visuelle et fonctionnalités

Chaque indicateur renvoyé par l'API fait l'objet d'un panneau dédié comprenant :

| Élément                    | Description                                                                    | Exemple                                                                           |
|----------------------------|--------------------------------------------------------------------------------|-----------------------------------------------------------------------------------|
| **Label**                  | Intitulé de l'indicateur électrique                                            | *Facteur de puissance*, *Voltage*, *Taux de charge*                               |
| **Valeur & unité**         | Mesure formatée avec `Intl.NumberFormat('fr-FR')` et son unité                 | `0,96`, `402,5 V`, `42,7 %` (ou `—` si null)                                      |
| **Qualité & code couleur** | Badge et bordure latérale colorée selon l'état de l'indicateur                 | Voir tableau ci-dessous                                                           |
| **Recommandation courte**  | Synthèse immédiate de la situation                                             | *« Tension stable et optimale. Vos équipements fonctionnent en toute sécurité. »* |
| **Recommandation longue**  | Encadré dépliable au clic sur le bouton **« Voir plus »** / **« Voir moins »** | Recommandation détaillée avec plan d'action préventif ou correctif                |

### Niveaux de qualité et codes couleur

| Qualité API | Libellé affiché  | Couleur de bordure et texte | Fond du badge |
|-------------|------------------|-----------------------------|---------------|
| `good`      | **Optimale**     | Vert (`#1f7a63`)            | `#eef7f4`     |
| `medium`    | **À surveiller** | Orange (`#8a5a00`)          | `#fdf3dc`     |
| `bad`       | **Critique**     | Rouge (`#b23a48`)           | `#fbeaec`     |
| `unknown`   | **Indisponible** | Gris neutre (`#5b6573`)     | `#f3f4f6`     |

---

## 3. Gestion des états et accessibilité

Conformément aux conventions de l'application :

- **Chargement** : affiche un texte discret « Chargement… » pendant la requête initiale.
- **Erreur API** : bloc d'alerte avec fond rouge clair et `role="alert"` (« Recommandations indisponibles. »).
- **Absence de données (204 No Content ou liste vide)** : affiche « Aucune recommandation disponible pour ce site. ».
- **Accessibilité** :
  - Section repérée par `aria-labelledby="recommendations-title"`.
  - Bouton bascule « Voir plus » doté de `[attr.aria-expanded]` et `[attr.aria-controls]`.
  - Éléments clés identifiés par des attributs `data-testid` (`recommendation-item`, `recommendation-label`, `recommendation-value`, `recommendation-quality`, `toggle-more`, `recommendation-long`).

