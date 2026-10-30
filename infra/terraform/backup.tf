# MVP: daily full copies, immutable for seven days, in the existing account/region.
# SSE-S3 avoids introducing a customer KMS key whose deletion could destroy recovery.
resource "aws_s3_bucket" "backup" {
  bucket              = "${local.name}-backup-${data.aws_caller_identity.current.account_id}"
  object_lock_enabled = true

  lifecycle {
    prevent_destroy = true
  }
}

# S3 access-log targets cannot have Object Lock; use a private prefix of the deployment bucket.
resource "aws_s3_bucket_logging" "backup" {
  bucket        = aws_s3_bucket.backup.id
  target_bucket = aws_s3_bucket.deploy.id
  target_prefix = "access-logs/backup/"
  depends_on    = [aws_s3_bucket_policy.deploy_access_logs]
}

data "aws_iam_policy_document" "deploy_access_logs" {
  statement {
    sid       = "AllowBackupAccessLogs"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.deploy.arn}/access-logs/backup/*"]
    principals {
      type        = "Service"
      identifiers = ["logging.s3.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_s3_bucket.backup.arn]
    }
  }
  statement {
    sid       = "RequireTLS"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.deploy.arn, "${aws_s3_bucket.deploy.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "deploy_access_logs" {
  bucket = aws_s3_bucket.deploy.id
  policy = data.aws_iam_policy_document.deploy_access_logs.json
}

resource "aws_s3_bucket_public_access_block" "backup" {
  bucket                  = aws_s3_bucket.backup.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "backup" {
  bucket = aws_s3_bucket.backup.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "backup" {
  bucket = aws_s3_bucket.backup.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "backup" {
  bucket = aws_s3_bucket.backup.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_object_lock_configuration" "backup" {
  bucket     = aws_s3_bucket.backup.id
  depends_on = [aws_s3_bucket_versioning.backup]
  rule {
    default_retention {
      mode = "COMPLIANCE"
      days = 7
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "backup" {
  bucket = aws_s3_bucket.backup.id
  rule {
    id     = "seven-day-mvp-backups"
    status = "Enabled"
    filter {
      prefix = "runs/"
    }
    expiration {
      days = 7
    }
    noncurrent_version_expiration {
      noncurrent_days = 1
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

data "aws_iam_policy_document" "backup_bucket" {
  statement {
    sid       = "RequireTLS"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.backup.arn, "${aws_s3_bucket.backup.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "backup" {
  bucket = aws_s3_bucket.backup.id
  policy = data.aws_iam_policy_document.backup_bucket.json
}

# The EC2 can upload dumps, but cannot read or delete backups.
resource "aws_iam_role_policy" "app_backup" {
  role = aws_iam_role.app.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:PutObject", "s3:AbortMultipartUpload"]
      Resource = ["${aws_s3_bucket.backup.arn}/runs/*/db/*", "${aws_s3_bucket.backup.arn}/runs/*/logs/app/*"]
    }]
  })
}

resource "aws_iam_role_policy" "monitoring_backup" {
  role = aws_iam_role.monitoring.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:PutObject", "s3:AbortMultipartUpload"]
      Resource = "${aws_s3_bucket.backup.arn}/runs/*/logs/monitoring/*"
    }]
  })
}

resource "aws_ssm_document" "backup_logs" {
  for_each = {
    app        = "enervision"
    monitoring = "enervision-monitoring"
  }
  name            = "${local.name}-backup-logs-${each.key}"
  document_type   = "Command"
  document_format = "JSON"
  content = jsonencode({
    schemaVersion = "2.2"
    description   = "Export host, Docker and Loki logs to immutable backups"
    parameters = {
      RunId = {
        type           = "String"
        allowedPattern = "^[0-9]{8}T[0-9]{6}Z-[a-f0-9]{12}$"
      }
    }
    mainSteps = [{
      action = "aws:runShellScript"
      name   = "ExportLogs"
      inputs = {
        timeoutSeconds = "1800"
        runCommand = [
          "set -eu",
          "export AWS_DEFAULT_REGION='${var.region}' BACKUP_BUCKET='${aws_s3_bucket.backup.bucket}' BACKUP_RUN_ID='{{ RunId }}' BACKUP_HOST='${each.key}' BACKUP_PROJECT='${each.value}'",
          "python3 - <<'ENERVISION_LOG_BACKUP_PY'\n${file("${path.module}/../backup/dump_host.py")}\nENERVISION_LOG_BACKUP_PY"
        ]
      }
    }]
  })
}

# Fixed commands: the backup role cannot submit an arbitrary root shell over SSM.
resource "aws_ssm_document" "backup" {
  name            = "${local.name}-backup-database"
  document_type   = "Command"
  document_format = "JSON"
  content = jsonencode({
    schemaVersion = "2.2"
    description   = "Dump PostgreSQL databases into immutable S3 backups"
    parameters = {
      RunId = {
        type           = "String"
        allowedPattern = "^[0-9]{8}T[0-9]{6}Z-[a-f0-9]{12}$"
      }
    }
    mainSteps = [{
      action = "aws:runShellScript"
      name   = "DumpDatabase"
      inputs = {
        timeoutSeconds = "1800"
        runCommand = [
          "set -eu",
          "export AWS_DEFAULT_REGION='${var.region}' BACKUP_BUCKET='${aws_s3_bucket.backup.bucket}' BACKUP_RUN_ID='{{ RunId }}'",
          "python3 - <<'ENERVISION_BACKUP_PY'\n${file("${path.module}/../backup/dump_db.py")}\nENERVISION_BACKUP_PY"
        ]
      }
    }]
  })
}

data "aws_iam_policy_document" "backup_assume" {
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
      values   = ["${var.github_oidc_sub_prefix}:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_role" "backup" {
  name                 = "${local.name}-github-backup"
  assume_role_policy   = data.aws_iam_policy_document.backup_assume.json
  max_session_duration = 7200
}

locals {
  tfstate_bucket_arn = "arn:aws:s3:::enervision-tfstate-s3"
}

resource "aws_iam_role_policy" "backup" {
  role = aws_iam_role.backup.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ssm:GetParameter"]
        Resource = [aws_ssm_parameter.backup.arn, "arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter/${local.name}/prod/deployed-sha"]
      },
      {
        Effect   = "Allow"
        Action   = ["ssm:GetParametersByPath"]
        Resource = [for path in ["env", "monitoring"] : "arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter/${local.name}/prod/${path}"]
      },
      {
        Effect   = "Allow"
        Action   = ["ssm:SendCommand"]
        Resource = concat([aws_ssm_document.backup.arn, aws_instance.app.arn, aws_instance.monitoring.arn], [for document in aws_ssm_document.backup_logs : document.arn])
      },
      {
        Effect   = "Allow"
        Action   = ["ssm:GetCommandInvocation"]
        Resource = "*" # This API does not support resource-level permissions.
      },
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = [aws_s3_bucket.datalake.arn, aws_s3_bucket.deploy.arn, local.tfstate_bucket_arn, aws_s3_bucket.backup.arn]
      },
      {
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:GetObjectVersion"]
        Resource = [
          "${aws_s3_bucket.datalake.arn}/*", "${aws_s3_bucket.deploy.arn}/releases/*",
          "${local.tfstate_bucket_arn}/prod/terraform.tfstate", "${aws_s3_bucket.backup.arn}/runs/*"
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:AbortMultipartUpload", "s3:GetObjectRetention"]
        Resource = "${aws_s3_bucket.backup.arn}/runs/*"
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetBucketObjectLockConfiguration"]
        Resource = aws_s3_bucket.backup.arn
      },
      {
        Effect   = "Allow"
        Action   = ["kms:Decrypt"]
        Resource = "arn:aws:kms:${var.region}:${data.aws_caller_identity.current.account_id}:key/*"
        Condition = {
          StringEquals = { "kms:ViaService" = "s3.${var.region}.amazonaws.com" }
          StringLike = {
            "kms:EncryptionContext:aws:s3:arn" = [local.tfstate_bucket_arn, "${local.tfstate_bucket_arn}/prod/terraform.tfstate"]
          }
        }
      },
      {
        Effect   = "Allow"
        Action   = ["kms:Decrypt"]
        Resource = "arn:aws:kms:${var.region}:${data.aws_caller_identity.current.account_id}:key/*"
        Condition = {
          StringEquals = { "kms:ViaService" = "ssm.${var.region}.amazonaws.com" }
          StringLike = {
            "kms:EncryptionContext:PARAMETER_ARN" = [for path in ["env", "monitoring"] : "arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter/${local.name}/prod/${path}/*"]
          }
        }
      }
    ]
  })
}

resource "aws_ssm_parameter" "backup" {
  name = "/${local.name}/prod/backup"
  type = "String" # Resource identifiers only, no credentials.
  value = jsonencode({
    bucket      = aws_s3_bucket.backup.bucket
    instance_id = aws_instance.app.id
    document    = aws_ssm_document.backup.name
    log_hosts = [
      { name = "app", instance_id = aws_instance.app.id, document = aws_ssm_document.backup_logs["app"].name },
      { name = "monitoring", instance_id = aws_instance.monitoring.id, document = aws_ssm_document.backup_logs["monitoring"].name }
    ]
    parameter_paths        = ["/${local.name}/prod/env", "/${local.name}/prod/monitoring"]
    deployed_sha_parameter = "/${local.name}/prod/deployed-sha"
    sources = [
      { bucket = aws_s3_bucket.datalake.bucket, prefix = "" },
      { bucket = aws_s3_bucket.deploy.bucket, prefix = "releases/" },
      { bucket = "enervision-tfstate-s3", prefix = "prod/terraform.tfstate", key = "prod/terraform.tfstate" }
    ]
  })
}

output "backup_bucket" {
  value = aws_s3_bucket.backup.bucket
}

output "backup_role_arn" {
  description = "Set repository variable AWS_BACKUP_ROLE_ARN to enable daily backups."
  value       = aws_iam_role.backup.arn
}
