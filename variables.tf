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

# GitHub App Integration
variable "github_token" {
  description = "GitHub App installation token (short-lived)"
  type        = string
  sensitive   = true
  default     = ""
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
variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Availability zones for subnet distribution"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b", "us-east-1c"]
}

# EKS Configuration
variable "kubernetes_version" {
  description = "Kubernetes version for EKS"
  type        = string
  default     = "1.28"
}

variable "cluster_endpoint_public_access" {
  description = "Enable public access to cluster endpoint"
  type        = bool
  default     = true
}

# Node Pool Configuration - CPU Workers
variable "cpu_node_instance_types" {
  description = "Instance types for CPU worker nodes"
  type        = list(string)
  default     = ["m5.xlarge", "m5.2xlarge"]
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
    condition     = var.cpu_node_max_size >= var.cpu_node_min_size && var.cpu_node_max_size <= 20
    error_message = "CPU node max size must be between min_size and 20."
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
    condition     = var.gpu_node_max_size >= var.gpu_node_min_size && var.gpu_node_max_size <= 10
    error_message = "GPU node max size must be between min_size and 10."
  }
}

variable "gpu_node_desired_size" {
  description = "Desired number of GPU worker nodes"
  type        = number
  default     = 0
}

# Storage
variable "enable_ebs_csi_driver" {
  description = "Enable EBS CSI driver for persistent volumes"
  type        = bool
  default     = true
}

variable "storage_class_name" {
  description = "Name of the storage class for Ray persistent storage"
  type        = string
  default     = "ray-storage"
}

# Autoscaling
variable "enable_cluster_autoscaler" {
  description = "Enable Kubernetes cluster autoscaler"
  type        = bool
  default     = true
}

variable "autoscaler_scale_down_delay" {
  description = "Delay before scaling down unused nodes (minutes)"
  type        = number
  default     = 10
}

# Ray Configuration
variable "ray_namespace" {
  description = "Kubernetes namespace for Ray deployments"
  type        = string
  default     = "ray-system"
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
  default     = {}
}

# Cost Management
variable "enable_cost_allocation_tags" {
  description = "Enable detailed cost allocation tags"
  type        = bool
  default     = true
}
