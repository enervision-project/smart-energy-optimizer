output "url" {
  value = "https://${var.domain}"
}

output "instance_id" {
  value = aws_instance.app.id
}

output "deploy_role_arn" {
  value = aws_iam_role.github_deploy.arn
}

output "deploy_bucket" {
  value = aws_s3_bucket.deploy.bucket
}

output "datalake_bucket" {
  value = aws_s3_bucket.datalake.bucket
}

output "github_variables" {
  description = "À lancer une fois après l'apply pour brancher le workflow Services."
  value       = <<-EOT
    gh variable set AWS_DEPLOY_ROLE_ARN --body ${aws_iam_role.github_deploy.arn}
    gh variable set DEPLOY_BUCKET --body ${aws_s3_bucket.deploy.bucket}
  EOT
}
