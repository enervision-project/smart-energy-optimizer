# One EC2 running compose.yaml + compose.prod.yaml; no SSH: aws ssm start-session --target <instance_id>

data "aws_caller_identity" "current" {}

locals {
  name                    = "enervision"
  mlflow_artifacts_prefix = "mlflow/artifacts"
  ml_datasets_prefix      = "ml/datasets"
  # services with an image to build: one ECR repository each
  services = jsondecode(file("${path.module}/../../.github/services.json")).services
  images   = [for k, s in local.services : k if contains(keys(s), "build")]
}

# --- Network: default VPC, public subnet
data "aws_vpc" "default" {
  default = true
}

data "aws_subnet" "app" {
  vpc_id            = data.aws_vpc.default.id
  availability_zone = "${var.region}a"
  default_for_az    = true
}

resource "aws_security_group" "app" {
  name        = "${local.name}-app"
  description = "EnerVision : HTTP entrant uniquement"
  vpc_id      = data.aws_vpc.default.id
}

resource "aws_vpc_security_group_ingress_rule" "web" {
  # 80: Let's Encrypt challenge + HTTPS redirect; 443/udp: HTTP/3
  for_each          = { http = ["tcp", 80], https = ["tcp", 443], http3 = ["udp", 443] }
  security_group_id = aws_security_group.app.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = each.value[0]
  from_port         = each.value[1]
  to_port           = each.value[1]
}

moved {
  from = aws_vpc_security_group_ingress_rule.http
  to   = aws_vpc_security_group_ingress_rule.web["http"]
}

resource "aws_vpc_security_group_egress_rule" "all" {
  security_group_id = aws_security_group.app.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

# --- Instance
data "aws_ssm_parameter" "al2023" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

# separate volume to survive an instance replacement (TimescaleDB data)
resource "aws_ebs_volume" "data" {
  availability_zone = data.aws_subnet.app.availability_zone
  size              = var.data_volume_size
  type              = "gp3"
  encrypted         = true
  tags              = { Name = "${local.name}-data" }

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_instance" "app" {
  ami                         = data.aws_ssm_parameter.al2023.value
  instance_type               = var.instance_type
  subnet_id                   = data.aws_subnet.app.id
  vpc_security_group_ids      = [aws_security_group.app.id]
  iam_instance_profile        = aws_iam_instance_profile.app.name
  associate_public_ip_address = false # Public IP is provided by aws_eip.app below
  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    data_volume_id = aws_ebs_volume.data.id
  })

  metadata_options {
    http_tokens                 = "required" # IMDSv2
    http_put_response_hop_limit = 2          # containers (etl-worker): instance role to write to bronze
  }

  root_block_device {
    volume_size = 20
    volume_type = "gp3"
    encrypted   = true
  }

  tags = { Name = "${local.name}-app" } # used by the workflow to find the instance

  lifecycle {
    # a new AMI or user_data must not silently replace the instance
    ignore_changes = [ami, user_data]
  }
}

resource "aws_volume_attachment" "data" {
  device_name = "/dev/sdf"
  volume_id   = aws_ebs_volume.data.id
  instance_id = aws_instance.app.id
}

resource "aws_eip" "app" {
  instance = aws_instance.app.id
  domain   = "vpc"
  tags     = { Name = "${local.name}-app" }
}

# --- DNS
data "aws_route53_zone" "main" {
  name = var.domain
}

resource "aws_route53_record" "app" {
  for_each = toset([var.domain, "www.${var.domain}"])
  zone_id  = data.aws_route53_zone.main.zone_id
  name     = each.key
  type     = "A"
  ttl      = 300
  records  = [aws_eip.app.public_ip]
}

# --- Images
resource "aws_ecr_repository" "service" {
  for_each             = toset(local.images)
  name                 = "${local.name}/${each.key}"
  image_tag_mutability = "MUTABLE" # latest tag

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "service" {
  for_each   = aws_ecr_repository.service
  repository = each.value.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "garde les 20 dernières images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 20 }
      action       = { type = "expire" }
    }]
  })
}

# --- Release files (compose, scripts), copied to the instance on each deployment
resource "aws_s3_bucket" "deploy" {
  bucket = "${local.name}-deploy-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_public_access_block" "deploy" {
  bucket                  = aws_s3_bucket.deploy.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "deploy" {
  bucket = aws_s3_bucket.deploy.id

  rule {
    id     = "backup-access-logs"
    status = "Enabled"
    filter {
      prefix = "access-logs/backup/"
    }
    expiration {
      days = 7
    }
  }

  rule {
    id     = "releases"
    status = "Enabled"
    filter {
      prefix = "releases/"
    }
    expiration {
      days = 30
    }
  }
}

# --- Data lake: raw ETL data (bronze/), private and encrypted
resource "aws_s3_bucket" "datalake" {
  bucket = "${local.name}-datalake-${data.aws_caller_identity.current.account_id}"

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_public_access_block" "datalake" {
  bucket                  = aws_s3_bucket.datalake.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "datalake" {
  bucket = aws_s3_bucket.datalake.id
  versioning_configuration {
    status = "Enabled" # an overwrite or deletion does not lose raw data
  }
}

# --- Production .env: /enervision/prod/env/<NAME>, read on each deployment
resource "random_password" "db" {
  length  = 32
  special = false # no $ or characters to escape in .env / the URL
}

# Dedicated PostgreSQL account for MLflow; no local value reused in production.
resource "random_password" "mlflow_db" {
  length  = 32
  special = false
}

# PostgreSQL role of the Postgres exporter (Alloy), managed by db-bootstrap
resource "random_password" "monitoring_db" {
  length  = 32
  special = false
}

# first core-api ADMIN password; read: aws ssm get-parameter --with-decryption --name /enervision/prod/env/ADMIN_PASSWORD
# lecture : aws ssm get-parameter --with-decryption --name /enervision/prod/env/ADMIN_PASSWORD
resource "random_password" "admin" {
  length  = 24
  special = false
}

# core-api HMAC key: 32 random bytes, Base64-encoded
resource "random_bytes" "jwt" {
  length = 32
}

resource "random_password" "service_db" {
  for_each = toset(["core_api", "etl_worker", "prediction_jobs", "enervision_migrator"])
  length   = 32
  # URL-safe credentials for the two psycopg connection URLs.
  special = false
}

locals {
  db_user = "enervision"
  db_name = "enervision"
  # ENERGY_API_USERNAME / ENERGY_API_PASSWORD: written by the Deploy workflow from GitHub secrets.
  env = merge(var.app_env, {
    POSTGRES_USER                = local.db_user
    POSTGRES_PASSWORD            = random_password.db.result
    POSTGRES_DB                  = local.db_name
    CORE_API_DB_PASSWORD         = random_password.service_db["core_api"].result
    ETL_DB_PASSWORD              = random_password.service_db["etl_worker"].result
    PREDICTION_DB_PASSWORD       = random_password.service_db["prediction_jobs"].result
    MIGRATOR_DB_PASSWORD         = random_password.service_db["enervision_migrator"].result
    ETL_DATABASE_URL             = "postgresql://etl_worker:${random_password.service_db["etl_worker"].result}@db:5432/${local.db_name}"
    PREDICTION_DATABASE_URL      = "postgresql://prediction_jobs:${random_password.service_db["prediction_jobs"].result}@db:5432/${local.db_name}"
    ENERGY_API_BASE_URL          = var.energy_api_base_url
    BRONZE_BUCKET                = aws_s3_bucket.datalake.bucket
    AWS_DEFAULT_REGION           = var.region
    DOMAIN                       = var.domain
    JWT_SECRET                   = random_bytes.jwt.base64
    ADMIN_EMAIL                  = "admin@${var.domain}"
    ADMIN_PASSWORD               = random_password.admin.result
    MLFLOW_DB_NAME               = "mlflow"
    MLFLOW_DB_USER               = "mlflow"
    MLFLOW_DB_PASSWORD           = random_password.mlflow_db.result
    MLFLOW_ARTIFACTS_DESTINATION = "s3://${aws_s3_bucket.datalake.bucket}/${local.mlflow_artifacts_prefix}"
    TRAINING_BOOTSTRAP_URI       = "s3://${aws_s3_bucket.datalake.bucket}/${local.ml_datasets_prefix}/bootstrap/v1"
    # Alloy pushes metrics and logs to the monitoring EC2 (VPC private IP)
    MONITORING_HOST        = aws_instance.monitoring.private_ip
    MONITORING_DB_PASSWORD = random_password.monitoring_db.result
  })
}

resource "aws_ssm_parameter" "env" {
  for_each = setsubtract(toset(nonsensitive(keys(local.env))), toset(["TRAINING_BOOTSTRAP_URI"]))
  name     = "/${local.name}/prod/env/${each.key}"
  type     = "SecureString"
  value    = local.env[each.key]
}
# The existing parameter is kept; Deploy then drives the active version.
moved {
  from = aws_ssm_parameter.env["TRAINING_BOOTSTRAP_URI"]
  to   = aws_ssm_parameter.training_bootstrap_uri
}

resource "aws_ssm_parameter" "training_bootstrap_uri" {
  name  = "/${local.name}/prod/env/TRAINING_BOOTSTRAP_URI"
  type  = "SecureString"
  value = local.env["TRAINING_BOOTSTRAP_URI"]

  lifecycle {
    ignore_changes = [value]
  }
}
