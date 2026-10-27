# Dedicated EC2 for monitoring stack
# Alloy pushes metrics and logs over the VPC private network
# Grafana is public on grafana.<domain> (HTTPS, Caddy), login through GitHub OAuth

# --- Network: only the app security group can push
resource "aws_security_group" "monitoring" {
  name = "${local.name}-monitoring"
  # outdated since Grafana is public (80/443), but changing it would replace the security group
  description = "EnerVision monitoring: inbound from the app EC2 only"
  vpc_id      = data.aws_vpc.default.id
}

resource "aws_vpc_security_group_ingress_rule" "monitoring" {
  # 9090: Prometheus remote write; 3100: Loki push
  for_each                     = { prometheus = 9090, loki = 3100 }
  security_group_id            = aws_security_group.monitoring.id
  referenced_security_group_id = aws_security_group.app.id
  ip_protocol                  = "tcp"
  from_port                    = each.value
  to_port                      = each.value
}

resource "aws_vpc_security_group_ingress_rule" "monitoring_web" {
  # Grafana through Caddy: 443 HTTPS; 80 Let's Encrypt challenge + redirect to HTTPS
  for_each          = { http = 80, https = 443 }
  security_group_id = aws_security_group.monitoring.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = each.value
  to_port           = each.value
}

resource "aws_vpc_security_group_egress_rule" "monitoring" {
  # default VPC without NAT: public egress for SSM, S3 and Docker images
  security_group_id = aws_security_group.monitoring.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

# --- Instance (arm64): history on the root volume, lost if the instance is replaced
data "aws_ssm_parameter" "al2023_arm64" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

resource "aws_instance" "monitoring" {
  ami                         = data.aws_ssm_parameter.al2023_arm64.value
  instance_type               = var.monitoring_instance_type
  subnet_id                   = data.aws_subnet.app.id
  vpc_security_group_ids      = [aws_security_group.monitoring.id]
  iam_instance_profile        = aws_iam_instance_profile.monitoring.name
  associate_public_ip_address = true # replaced by the Elastic IP below
  user_data                   = file("${path.module}/monitoring_user_data.sh")

  metadata_options {
    http_tokens = "required" # IMDSv2
  }

  root_block_device {
    volume_size = var.monitoring_volume_size
    volume_type = "gp3"
    encrypted   = true
  }

  tags = { Name = "${local.name}-monitoring" } # used by the deploy workflow to find the instance

  lifecycle {
    ignore_changes = [ami, user_data]
  }
}

# fixed public IP: the DNS record survives a stop / start of the instance
resource "aws_eip" "monitoring" {
  instance = aws_instance.monitoring.id
  domain   = "vpc"
  tags     = { Name = "${local.name}-monitoring" }
}

resource "aws_route53_record" "grafana" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = local.grafana_domain
  type    = "A"
  ttl     = 300
  records = [aws_eip.monitoring.public_ip]
}

# --- Monitoring .env: /enervision/prod/monitoring/<NAME>, read on each deploy
# read: aws ssm get-parameter --with-decryption --name /enervision/prod/monitoring/GRAFANA_ADMIN_PASSWORD
resource "random_password" "grafana_admin" {
  length  = 24
  special = false
}

locals {
  grafana_domain = "grafana.${var.domain}"
  monitoring_env = {
    GRAFANA_ADMIN_PASSWORD = random_password.grafana_admin.result
    GRAFANA_DOMAIN         = local.grafana_domain
    GRAFANA_ROOT_URL       = "https://${local.grafana_domain}"
    GITHUB_OAUTH_CLIENT_ID = var.grafana_github_client_id
  }
}

resource "aws_ssm_parameter" "monitoring_env" {
  for_each = toset(nonsensitive(keys(local.monitoring_env)))
  name     = "/${local.name}/prod/monitoring/${each.key}"
  type     = "SecureString"
  value    = local.monitoring_env[each.key]
}

# GitHub OAuth app secret: never in git or tfvars, set by hand after the first apply:
#   aws ssm put-parameter --overwrite --type SecureString \
#     --name /enervision/prod/monitoring/GITHUB_OAUTH_CLIENT_SECRET --value '<secret>'
resource "aws_ssm_parameter" "github_oauth_client_secret" {
  name  = "/${local.name}/prod/monitoring/GITHUB_OAUTH_CLIENT_SECRET"
  type  = "SecureString"
  value = "set-me-by-hand"

  lifecycle {
    ignore_changes = [value]
  }
}
