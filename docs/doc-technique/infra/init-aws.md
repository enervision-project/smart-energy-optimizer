# Init AWS user

Mise en place d'un poste de développeur, à faire une seule fois : installation des outils
(AWS CLI, GitHub CLI, Terraform), puis connexion à GitHub et à AWS.

!!! info "Prérequis"
    Linux ou WSL, avec `curl`, `unzip` et `python3` (`sudo apt install curl unzip python3`).
    Il faut aussi un compte dans **IAM Identity Center** (SSO AWS) et être membre de
    l'organisation GitHub `enervision-project` : à demander à l'équipe.

## 1. Installer les outils

```bash
cd ~/work/smart-energy-optimizer
scripts/aws/install-tools.sh
source ~/.bashrc
```

Le script installe **AWS CLI v2**, **Terraform** et **gh** dans `~/.local/bin` (sans `sudo`),
et ajoute `export AWS_PROFILE=enervision` à `~/.bashrc` : toutes les commandes `aws` et
`terraform` utilisent alors le profil `enervision` sans avoir à le préciser.

Vérification :

```bash
aws --version && terraform version && gh --version
```

## 2. Se connecter à GitHub

```bash
gh auth login
```

Choisir **GitHub.com** → **SSH** → laisser gh **générer une nouvelle clé SSH** et l'envoyer
sur ton compte → **Login with a web browser**. Le dépôt utilise un remote `git@github.com:`,
la clé SSH est donc nécessaire pour `git pull` / `git push`.

Vérification :

```bash
gh auth status
gh repo view enervision-project/smart-energy-optimizer --json name
```

## 3. Se connecter à AWS (SSO)

La connexion passe par le SSO : aucune clé d'accès à créer ni à stocker.

Les valeurs de connexion (session, URL du portail, région) ne sont pas publiées dans cette
documentation : elles sont dans la variable **`AWS_VARIABLE_DEV_INIT`** du dépôt, visible
dans [Settings → Secrets and variables → Actions → Variables](https://github.com/enervision-project/smart-energy-optimizer/settings/variables/actions)
ou directement depuis le terminal :

```bash
gh variable get AWS_VARIABLE_DEV_INIT -R enervision-project/smart-energy-optimizer
```

```bash
aws configure sso
```

| Question | Réponse |
|---|---|
| SSO session name | valeur de `AWS_VARIABLE_DEV_INIT` |
| SSO start URL | valeur de `AWS_VARIABLE_DEV_INIT` |
| SSO region | valeur de `AWS_VARIABLE_DEV_INIT` |
| SSO registration scopes | Entrée (valeur par défaut) |
| Compte / rôle | le compte EnerVision, rôle `AdministratorAccess` |
| Default client Region | `eu-west-3` |
| CLI default output format | `json` |
| Profile name | `enervision` (nom attendu par les scripts) |

Le navigateur s'ouvre pour valider la connexion. Sans navigateur (SSH), ajouter
`--use-device-code` et ouvrir le lien affiché depuis une autre machine.

Vérification :

```bash
aws sts get-caller-identity   # doit afficher le compte et le rôle AdministratorAccess
```

!!! tip "Session expirée"
    La session SSO dure quelques heures. Quand une commande renvoie une erreur de token
    expiré : `aws sso login`.

## 4. Préparer Terraform

Uniquement pour modifier l'infrastructure : le déploiement des services est fait par la CI
(voir [Déploiement CI/CD](deploiement.md)).

Deux fichiers locaux, **jamais versionnés** (ils sont dans `../../../.gitignore`), sont à créer à partir
de leurs modèles :

```bash
cd infra/terraform
cp backend.hcl.example backend.hcl            # emplacement du state (bucket S3 partagé)
cp terraform.tfvars.example terraform.tfvars  # variables du projet
```

Dans `terraform.tfvars`, renseigner l'URL de l'API énergie :

```hcl
energy_api_base_url = "https://api-mock.charlieandre.fr/"
```

Puis initialiser et vérifier que tout est à jour :

```bash
terraform init -backend-config=backend.hcl
terraform plan        # « No changes » si l'infra correspond au code
```

!!! warning "State partagé"
    Le state est commun à toute l'équipe (bucket `enervision-tfstate-s3`, verrouillé pendant
    un `plan` ou un `apply`). Toujours relire le `plan` avant un `terraform apply`, et ne
    lancer `apply` que depuis une branche à jour avec `main`.

## Récapitulatif

| Outil | Connexion | Quand la refaire |
|---|---|---|
| gh | `gh auth login` | une fois par machine |
| AWS CLI | `aws configure sso` | une fois ; ensuite `aws sso login` à l'expiration |
| Terraform | `terraform init -backend-config=backend.hcl` | une fois, puis après un changement de provider |
