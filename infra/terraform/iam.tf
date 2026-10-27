# --- Rôle de l'instance : SSM (agent + paramètres .env), lecture ECR et S3
data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "app" {
  name               = "${local.name}-app"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

resource "aws_iam_role_policy_attachment" "app" {
  for_each = toset([
    "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
    "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
  ])
  role       = aws_iam_role.app.name
  policy_arn = each.key
}

data "aws_iam_policy_document" "app" {
  statement {
    actions   = ["ssm:GetParametersByPath"]
    resources = ["arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter/${local.name}/prod/env"]
  }
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.deploy.arn}/releases/*"]
  }
  statement {
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.deploy.arn]
  }
  statement {
    # etl-worker : écriture seule des mesures brutes
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.datalake.arn}/bronze/readings/*"]
  }
  statement {
    # MLflow : lister uniquement son prefixe, sans ouvrir la lecture du bronze.
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.datalake.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        local.mlflow_artifacts_prefix, "${local.mlflow_artifacts_prefix}/*",
        local.ml_datasets_prefix, "${local.ml_datasets_prefix}/*",
      ]
    }
  }
  statement {
    # Les uploads multipart utilisent PutObject ; Abort permet de nettoyer un echec.
    actions = [
      "s3:GetObject", "s3:PutObject", "s3:AbortMultipartUpload",
    ]
    resources = ["${aws_s3_bucket.datalake.arn}/${local.mlflow_artifacts_prefix}/*"]
  }
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.datalake.arn}/${local.ml_datasets_prefix}/*"]
  }
}

resource "aws_iam_role_policy" "app" {
  role   = aws_iam_role.app.id
  policy = data.aws_iam_policy_document.app.json
}

resource "aws_iam_instance_profile" "app" {
  name = "${local.name}-app"
  role = aws_iam_role.app.name
}

# --- Monitoring instance role: SSM (agent + parameters), read S3 releases
resource "aws_iam_role" "monitoring" {
  name               = "${local.name}-monitoring"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

resource "aws_iam_role_policy_attachment" "monitoring" {
  role       = aws_iam_role.monitoring.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "monitoring" {
  statement {
    actions   = ["ssm:GetParametersByPath"]
    resources = ["arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter/${local.name}/prod/monitoring"]
  }
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.deploy.arn}/releases/*"]
  }
  statement {
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.deploy.arn]
  }
}

resource "aws_iam_role_policy" "monitoring" {
  role   = aws_iam_role.monitoring.id
  policy = data.aws_iam_policy_document.monitoring.json
}

resource "aws_iam_instance_profile" "monitoring" {
  name = "${local.name}-monitoring"
  role = aws_iam_role.monitoring.name
}

# --- GitHub Actions (OIDC) : push ECR + déploiement SSM, depuis main uniquement
resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

data "aws_iam_policy_document" "github_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    # jobs without environment (changes, build) get a ref sub; the deploy job, gated by the
    # production environment (required reviewers, main branch only), gets an environment sub
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "${var.github_oidc_sub_prefix}:ref:refs/heads/main",
        "${var.github_oidc_sub_prefix}:environment:production",
      ]
    }
  }
}

resource "aws_iam_role" "github_deploy" {
  name               = "${local.name}-github-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_assume.json
}

data "aws_iam_policy_document" "github_deploy" {
  statement {
    actions   = ["ecr:GetAuthorizationToken", "ec2:DescribeInstances", "ssm:GetCommandInvocation"]
    resources = ["*"]
  }
  statement {
    actions = [
      "ecr:BatchCheckLayerAvailability", "ecr:BatchGetImage", "ecr:CompleteLayerUpload",
      "ecr:GetDownloadUrlForLayer", "ecr:InitiateLayerUpload", "ecr:PutImage", "ecr:UploadLayerPart",
    ]
    resources = [for r in aws_ecr_repository.service : r.arn]
  }
  statement {
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.deploy.arn}/releases/*"]
  }
  # Données choisies par DVC : lecture du cache et publication des snapshots uniquement.
  statement {
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.datalake.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        "${local.ml_datasets_prefix}/dvc", "${local.ml_datasets_prefix}/dvc/*",
        "${local.ml_datasets_prefix}/bootstrap", "${local.ml_datasets_prefix}/bootstrap/*",
      ]
    }
  }
  statement {
    actions = ["s3:GetObject"]
    resources = [
      "${aws_s3_bucket.datalake.arn}/${local.ml_datasets_prefix}/dvc/*",
      "${aws_s3_bucket.datalake.arn}/${local.ml_datasets_prefix}/bootstrap/*",
    ]
  }
  statement {
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.datalake.arn}/${local.ml_datasets_prefix}/bootstrap/*"]
  }
  statement {
    actions   = ["ssm:GetParameter", "ssm:PutParameter"]
    resources = ["arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter/${local.name}/prod/env/TRAINING_BOOTSTRAP_URI"]
  }
  statement {
    actions   = ["ssm:SendCommand"]
    resources = [aws_instance.app.arn, aws_instance.monitoring.arn, "arn:aws:ssm:${var.region}::document/AWS-RunShellScript"]
  }
  statement {
    actions   = ["ssm:GetParameter", "ssm:PutParameter"]
    resources = ["arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter/${local.name}/prod/deployed-sha"]
  }
  statement {
    # identifiants de l'API énergie : source de vérité = secrets GitHub, recopiés à chaque déploiement
    actions = ["ssm:PutParameter"]
    resources = [for k in ["ENERGY_API_USERNAME", "ENERGY_API_PASSWORD"] :
    "arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter/${local.name}/prod/env/${k}"]
  }
}

resource "aws_iam_role_policy" "github_deploy" {
  role   = aws_iam_role.github_deploy.id
  policy = data.aws_iam_policy_document.github_deploy.json
}

# --- GitHub Actions (OIDC): read-only terraform plan, from the repository pull requests
# Pull requests from forks get no OIDC token: only repository members can use this role.
data "aws_iam_policy_document" "github_plan_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["${var.github_oidc_sub_prefix}:pull_request"]
    }
  }
}

resource "aws_iam_role" "github_plan" {
  name                 = "${local.name}-github-plan"
  assume_role_policy   = data.aws_iam_policy_document.github_plan_assume.json
  max_session_duration = 3600
}

# reads every managed resource and the state (S3 bucket); no write access,
# hence the plan runs with -lock=false
resource "aws_iam_role_policy_attachment" "github_plan" {
  role       = aws_iam_role.github_plan.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}
