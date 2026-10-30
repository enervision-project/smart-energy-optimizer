terraform {
  required_version = ">= 1.10" # use_lockfile of the S3 backend

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # partial configuration: terraform init -backend-config=backend.hcl
  backend "s3" {}
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "enervision"
      ManagedBy = "terraform"
    }
  }
}
