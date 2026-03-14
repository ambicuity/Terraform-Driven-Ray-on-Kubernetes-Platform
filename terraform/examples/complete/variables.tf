variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "cluster_name" {
  description = "Name of the EKS cluster"
  type        = string
  default     = "example-ray-cluster"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "enable_velero" {
  description = "Deploy Velero as part of the complete example."
  type        = bool
  default     = false
}

variable "velero_backup_schedule" {
  description = "Cron expression for automated Velero backups."
  type        = string
  default     = "0 2 * * *"
}
