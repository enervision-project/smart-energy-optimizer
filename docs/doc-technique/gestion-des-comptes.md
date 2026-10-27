# Gestion des comptes

Il n'y a ni inscription ni écran d'administration. Le premier administrateur est créé automatiquement ; les autres comptes et leurs droits sur les sites se gèrent en SQL.

| Rôle | Voit |
|---|---|
| `ADMIN` | Tous les sites |
| `USER` | Uniquement les sites listés dans `users_sites` |

Fonctionnement côté API (jeton, règles d'accès) : voir la page Sécurité de core-api.

## Premier administrateur

Au démarrage, tant que la table `users` est vide, core-api crée un compte `ADMIN` à partir de `ADMIN_EMAIL` et `ADMIN_PASSWORD` (12 caractères minimum).

- **En local** : valeurs du `.env`.
- **En production** : générées par Terraform dans SSM. Mot de passe :

    ```bash
    aws ssm get-parameter --with-decryption \
      --name /enervision/prod/env/ADMIN_PASSWORD --query Parameter.Value --output text
    ```

## Ouvrir une session SQL

```bash
# local
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'

# production
aws ssm start-session --target <instance_id>
cd /opt/enervision
sudo docker compose -f compose.yaml -f compose.prod.yaml --env-file .env --env-file deploy.env \
  exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

## Créer un utilisateur

1. Hacher le mot de passe en BCrypt :

    ```bash
    docker run --rm docker.io/library/httpd:2.4-alpine htpasswd -nbBC 10 "" '<mot de passe>' | tr -d ':\n'
    ```

2. L'insérer, **précédé de `{bcrypt}`** et avec l'email **en minuscules** (la connexion compare l'email en minuscules) :

    ```sql
    INSERT INTO users (email, password, first_name, last_name, company_name, role)
    VALUES ('jane.doe@example.com', '{bcrypt}$2y$10$...', 'Jane', 'Doe', 'EnerVision', 'USER')
    RETURNING id;
    ```

## Donner accès à des sites

Un `USER` sans ligne dans `users_sites` se connecte mais ne voit aucun site.

```sql
-- un ou plusieurs sites
INSERT INTO users_sites (user_id, site_id)
SELECT id, site_id FROM users, sites
WHERE email = 'jane.doe@example.com' AND site_id IN ('SITE001', 'SITE002')
ON CONFLICT DO NOTHING;

-- retirer un site
DELETE FROM users_sites
WHERE site_id = 'SITE002'
  AND user_id = (SELECT id FROM users WHERE email = 'jane.doe@example.com');

-- vérifier
SELECT u.email, us.site_id
FROM users u JOIN users_sites us ON us.user_id = u.id
ORDER BY u.email, us.site_id;
```

Le changement est pris en compte à la requête suivante, sans reconnexion.

## Changer un rôle

Par l'API, avec un jeton administrateur :

```bash
curl -X PATCH https://<domaine>/api/v1/users/<user_id>/role \
  -H "Authorization: Bearer <jeton admin>" -H 'Content-Type: application/json' \
  -d '{"role":"ADMIN"}'
```

Le nouveau rôle s'applique au **prochain jeton** : l'utilisateur doit se reconnecter (le rôle est inscrit dans le jeton, valable 1 h).

## Supprimer un utilisateur

```sql
DELETE FROM users WHERE email = 'jane.doe@example.com';
```

Ses lignes `users_sites` sont supprimées avec lui (`ON DELETE CASCADE`). Un jeton déjà émis reste valable jusqu'à son expiration.
