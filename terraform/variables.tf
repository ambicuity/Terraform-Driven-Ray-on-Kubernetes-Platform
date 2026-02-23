# Core Configuration
variable "region" {
  description = "AWS region for infrastructure deployment"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (dev, staging, production)"
  type        = string
  default     = "production"

  validation {
    condition     = contains(["dev", "staging", "production"], var.environment)
    error_message = "Environment must be dev, staging, or production."
  }
}

variable "cluster_name" {
  description = "Name of the EKS cluster"
  type        = string
  default     = "ray-ml-cluster"
}



variable "repo_name" {
  description = "GitHub repository name for resource tagging"
  type        = string
  default     = "unknown"
}

variable "commit_sha" {
  description = "Git commit SHA for resource tagging"
  type        = string
  default     = "unknown"
}

# Networking
variable "vpc_id" {
  description = "ID of the existing VPC to deploy the EKS cluster into"
  type        = string
}

variable "subnet_ids" {
  description = "List of subnet IDs to deploy the EKS cluster and worker nodes into (preferably private subnets)"
  type        = list(string)
}

# EKS Configuration
variable "kubernetes_version" {
  description = "Kubernetes version for EKS"
  type        = string
  default     = "1.31"
}

variable "kms_key_arn" {
  description = "The Amazon Resource Name (ARN) of the KMS key to use for envelope encryption of Kubernetes secrets. If not provided, a new key will be created."
  type        = string
  default     = ""
}

variable "cluster_endpoint_public_access" {
  description = "Enable public access to cluster endpoint"
  type        = bool
  default     = false
}

variable "eks_addons" {
  description = "Map of EKS addons to enable"
  type        = map(any)
  default = {
    vpc-cni = {
      resolve_conflicts_on_create = "OVERWRITE"
      resolve_conflicts_on_update = "OVERWRITE"
    }
    kube-proxy = {
      resolve_conflicts_on_create = "OVERWRITE"
      resolve_conflicts_on_update = "OVERWRITE"
    }
    coredns = {
      resolve_conflicts_on_create = "OVERWRITE"
      resolve_conflicts_on_update = "OVERWRITE"
    }
  }
}


# Node Pool Configuration - CPU Workers
variable "cpu_node_instance_types" {
  description = "Instance types for CPU worker nodes"
  type        = list(string)
  default     = ["m6g.xlarge", "m6g.2xlarge"]
}

variable "cpu_node_min_size" {
  description = "Minimum number of CPU worker nodes"
  type        = number
  default     = 2

  validation {
    condition     = var.cpu_node_min_size >= 1 && var.cpu_node_min_size <= 10
    error_message = "CPU node min size must be between 1 and 10."
  }
}

variable "cpu_node_max_size" {
  description = "Maximum number of CPU worker nodes"
  type        = number
  default     = 10

  validation {
    condition     = var.cpu_node_max_size >= 1 && var.cpu_node_max_size <= 20
    error_message = "CPU node max size must be between 1 and 20."
  }
}

variable "cpu_node_desired_size" {
  description = "Desired number of CPU worker nodes"
  type        = number
  default     = 3
}

# Node Pool Configuration - GPU Workers
variable "enable_gpu_nodes" {
  description = "Enable GPU worker node pool"
  type        = bool
  default     = true
}

variable "gpu_node_instance_types" {
  description = "Instance types for GPU worker nodes"
  type        = list(string)
  default     = ["g4dn.xlarge", "g4dn.2xlarge"]
}

variable "gpu_node_min_size" {
  description = "Minimum number of GPU worker nodes"
  type        = number
  default     = 0

  validation {
    condition     = var.gpu_node_min_size >= 0 && var.gpu_node_min_size <= 5
    error_message = "GPU node min size must be between 0 and 5."
  }
}

variable "gpu_node_max_size" {
  description = "Maximum number of GPU worker nodes"
  type        = number
  default     = 5

  validation {
    condition     = var.gpu_node_max_size >= 0 && var.gpu_node_max_size <= 10
    error_message = "GPU node max size must be between 0 and 10."
  }
}

variable "gpu_node_desired_size" {
  description = "Desired number of GPU worker nodes"
  type        = number
  default     = 0
}

variable "cpu_capacity_type" {
  description = "Capacity type for CPU worker nodes (ON_DEMAND or SPOT)"
  type        = string
  default     = "ON_DEMAND"
}

variable "gpu_capacity_type" {
  description = "Capacity type for GPU worker nodes (ON_DEMAND or SPOT). Default is SPOT for cost optimization."
  type        = string
  default     = "SPOT"
}

# Storage
variable "enable_ebs_csi_driver" {
  description = "Enable EBS CSI driver for persistent volumes"
  type        = bool
  default     = true
}



# Autoscaling
variable "enable_cluster_autoscaler" {
  description = "Enable Kubernetes cluster autoscaler"
  type        = bool
  default     = true
}





# Monitoring
variable "enable_cloudwatch_logs" {
  description = "Enable CloudWatch logs for control plane"
  type        = bool
  default     = true
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 7
}

# Tags
variable "tags" {
  description = "Additional tags for all resources"
  type        = map(string)
  default = {
    ManagedBy   = "Terraform"
    Environment = "production"
    Service     = "Ray-ML-Platform"
    Repository  = "Terraform-Driven-Ray-on-Kubernetes-Platform"
  }
}


