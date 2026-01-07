terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.23"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.11"
    }
  }

  # Local backend for state management
  # State file stored locally in terraform directory
  # Note: For production use with teams, consider using remote backend (S3, GCS, Terraform Cloud)
  backend "local" {
    path = "terraform.tfstate"
  }
}

# Alternative: GCS backend for Google Cloud
# Uncomment and configure if using GCP
# backend "gcs" {
#   bucket = "your-terraform-state-bucket"
#   prefix = "terraform/state"
# }
