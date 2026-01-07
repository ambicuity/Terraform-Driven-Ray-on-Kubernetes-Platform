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

  # S3 backend for state management
  # Configured via CLI arguments in GitHub Actions
  backend "s3" {
    # bucket = provided via -backend-config
    # key    = provided via -backend-config
    # region = provided via -backend-config
    encrypt        = true
    dynamodb_table = "terraform-state-lock"
    
    # Tags for state file
    tags = {
      ManagedBy   = "terraform"
      Environment = "production"
      Purpose     = "state-storage"
    }
  }
}

# Alternative: GCS backend for Google Cloud
# Uncomment and configure if using GCP
# backend "gcs" {
#   bucket = "your-terraform-state-bucket"
#   prefix = "terraform/state"
# }
