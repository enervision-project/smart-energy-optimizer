output "url" {
  value = "https://${var.domain}"
}

output "instance_id" {
  value = aws_instance.app.id
}

output "monitoring_instance_id" {
  value = aws_instance.monitoring.id
}

output "grafana_url" {
  value = "https://${local.grafana_domain}"
}

output "grafana_tunnel" {
  description = "Grafana on http://localhost:13000 (user admin, password in SSM)."
  value       = <<-EOT
    aws ssm start-session --target ${aws_instance.monitoring.id} \
      --document-name AWS-StartPortForwardingSession \
      --parameters portNumber=3000,localPortNumber=13000
    aws ssm get-parameter --with-decryption --name /${local.name}/prod/monitoring/GRAFANA_ADMIN_PASSWORD \
      --query Parameter.Value --output text
  EOT
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
    gh secret set ENERGY_API_USERNAME   # source of truth, copied to SSM by the Deploy workflow
    gh secret set ENERGY_API_PASSWORD
  EOT
}
