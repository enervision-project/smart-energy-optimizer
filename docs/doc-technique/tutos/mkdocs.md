# Utilisation de MkDocs

MkDocs est un outil de gestion de la documentation en Mardown.

## Lancer le projet MkDocs principal


**Si c'est la première fois :**

1. Se placer à la racine du projet 
2. Création d'un .venv : ```python3 -m venv .venv```
3. Activer l'environnement virtuel : ```source .venv/bin/activate```
4. Installation de uv : https://docs.astral.sh/uv/getting-started/installation/ (copier la commande)
5. Synchroniser uv avec les uv.lock et pyproject.yaml : ```uv sync```
6. Lancer MkDocs : ```mkdocs serve``` (donne un lien)
7. Arrêter MkDocs : ```ctrl + C```

<br>

**Si c'est la au moins la seconde fois :**

1. Activer l'environnement virtuel : ```source .venv/bin/activate```
2. Lancer MkDocs : ```mkdocs serve```

!!! tip "Astuce" 
    Faire un ```uv sync``` avant d'ajouter manuellement un nouveau plugin.


## Comment créer un dossier ?
  
1. Aller dans le répertoire "/docs" soit de la racine soit du module concerné.
2. A l'endroit souhaité créer un dossier

!!! info "Nommage" 
    Le nom du dossier sera le nom affiché.

    !!! example "Exemple" 
        un dossier "ma-superbe-doc" s'affichera "Ma superbe doc" 

!!! info "Visibilité"
    Un dossier ne sera pas visible s'il n'a pas de fichier mardown sous lui !

## Comment créer un fichier ?

1. Aller dans le répertoire "/docs" soit de la racine soit du module concerné.
2. A l'endroit souhaité créer un fichier avec l'extention ```.md```
3. Dans ce fichier mettre : ```# Mon titre```

!!! info "Nommage"
    Ici, c'est "Mon Titre" qui sera affiché lors des recherches et en titre pricipale de la page.