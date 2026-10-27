variable "region" {
  type    = string
  default = "eu-west-3"
}

variable "github_oidc_sub_prefix" {
  description = <<-EOT
    Préfixe du claim sub des jetons OIDC du dépôt autorisé à déployer (depuis main uniquement).
    Le dépôt utilise le format immuable (noms suivis des identifiants) :
    gh api repos/enervision-project/smart-energy-optimizer/actions/oidc/customization/sub
  EOT
  type        = string
  default     = "repo:enervision-project@318340507/smart-energy-optimizer@1425361683"
}

variable "domain" {
  description = "Zone Route 53 existante : apex et www pointent vers l'EC2."
  type        = string
  default     = "ener-vision.click"
}

variable "instance_type" {
  type    = string
  default = "t3.medium"
}

variable "data_volume_size" {
  description = "Taille (Go) du volume EBS monté sur /var/lib/docker (images + données TimescaleDB)."
  type        = number
  default     = 20
}

variable "monitoring_instance_type" {
  description = "Monitoring EC2 (arm64): Prometheus + Loki + Grafana."
  type        = string
  default     = "t4g.small"
}

variable "monitoring_volume_size" {
  description = "Root volume size (GB) of the monitoring EC2 (15 d metrics + 7 d logs)."
  type        = number
  default     = 30
}

variable "grafana_github_client_id" {
  description = "Client ID (not secret) of the GitHub OAuth app used to log in to Grafana (enervision-project org)."
  type        = string
  default     = "Ov23liK5JyviC4Z1zeB7"
}

variable "energy_api_base_url" {
  description = "URL de l'API énergie (API Mock de l'école), joignable depuis l'EC2."
  type        = string
}


variable "app_env" {
  description = "Variables non secrètes ajoutées au .env de production."
  type        = map(string)
  default = {
    ETL_CRON  = "*/5 * * * *"
    LOG_LEVEL = "INFO"
  }
}
