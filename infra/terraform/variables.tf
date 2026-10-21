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

variable "energy_api_username" {
  description = "Identifiant HTTP Basic de l'API énergie (fourni par le formateur)."
  type        = string
}

variable "energy_api_password" {
  description = "Mot de passe HTTP Basic de l'API énergie (fourni par le formateur)."
  type        = string
  sensitive   = true
}

variable "app_env" {
  description = "Variables non secrètes ajoutées au .env de production."
  type        = map(string)
  default = {
    ETL_CRON  = "*/5 * * * *"
    LOG_LEVEL = "INFO"
  }
}
