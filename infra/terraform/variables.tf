variable "region" {
  type    = string
  default = "eu-west-3"
}

variable "github_repository" {
  description = "Dépôt autorisé à déployer (OIDC), depuis la branche main uniquement."
  type        = string
  default     = "enervision-project/smart-energy-optimizer"
}

variable "domain" {
  description = "Zone Route 53 existante : apex et www pointent vers l'EC2."
  type        = string
  default     = "ener-vision.click"
}

variable "instance_type" {
  type    = string
  default = "t3.small"
}

variable "data_volume_size" {
  description = "Taille (Go) du volume EBS monté sur /var/lib/docker (images + données TimescaleDB)."
  type        = number
  default     = 20
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
