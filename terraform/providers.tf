# AWS Provider Configuration
provider "aws" {
  region = var.region

  default_tags {
    tags = merge(
      var.tags,
      {
        ManagedBy    = "github-app"
        Repository   = var.repo_name
        Commit       = var.commit_sha
        Terraform    = "true"
        Environment  = var.environment
      }
    )
  }
}

# Kubernetes Provider
# Configured after EKS cluster creation
provider "kubernetes" {
  host                   = aws_eks_cluster.main.endpoint
  cluster_ca_certificate = base64decode(aws_eks_cluster.main.certificate_authority[0].data)
  
  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args = [
      "eks",
      "get-token",
      "--cluster-name",
      aws_eks_cluster.main.name,
      "--region",
      var.region
    ]
  }
}

# Helm Provider
provider "helm" {
  kubernetes {
    host                   = aws_eks_cluster.main.endpoint
    cluster_ca_certificate = base64decode(aws_eks_cluster.main.certificate_authority[0].data)
    
    exec {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args = [
        "eks",
        "get-token",
        "--cluster-name",
        aws_eks_cluster.main.name,
        "--region",
        var.region
      ]
    }
  }
}

# Data source for AWS account info
data "aws_caller_identity" "current" {}

data "aws_availability_zones" "available" {
  state = "available"
}
