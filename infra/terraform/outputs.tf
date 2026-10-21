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

output "plan_role_arn" {
  value = aws_iam_role.github_plan.arn
}

output "github_variables" {
  description = "Run once after the apply to wire the Services and Terraform CI workflows."
  value       = <<-EOT
    gh variable set AWS_DEPLOY_ROLE_ARN --body ${aws_iam_role.github_deploy.arn}
    gh variable set DEPLOY_BUCKET --body ${aws_s3_bucket.deploy.bucket}
    gh variable set AWS_PLAN_ROLE_ARN --body ${aws_iam_role.github_plan.arn}
    gh variable set ENERGY_API_BASE_URL --body ${var.energy_api_base_url}
    gh secret set ENERGY_API_USERNAME   # prompts for the value (terraform.tfvars)
    gh secret set ENERGY_API_PASSWORD   # prompts for the value (terraform.tfvars)
  EOT
}
