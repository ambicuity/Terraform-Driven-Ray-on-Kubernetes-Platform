provider "aws" {
  region = var.region
}

data "aws_eks_cluster_auth" "cluster" {
  name = module.ray_eks_cluster.cluster_name
}

provider "kubernetes" {
  host                   = module.ray_eks_cluster.cluster_endpoint
  cluster_ca_certificate = base64decode(module.ray_eks_cluster.cluster_certificate_authority)
  token                  = data.aws_eks_cluster_auth.cluster.token
}

module "vpc" {
  # checkov:skip=CKV_TF_1: Version-pinned registry module — commit hash not applicable for public registry sources
  source  = "terraform-aws-modules/vpc/aws"
  version = "6.6.0"

  name = "${var.cluster_name}-vpc"
  cidr = var.vpc_cidr

  azs             = ["${var.region}a", "${var.region}b", "${var.region}c"]
  private_subnets = [for k, v in ["a", "b", "c"] : cidrsubnet(var.vpc_cidr, 4, k)]
  public_subnets  = [for k, v in ["a", "b", "c"] : cidrsubnet(var.vpc_cidr, 4, k + 3)]

  enable_nat_gateway   = true
  single_nat_gateway   = true
  enable_dns_hostnames = true

  tags = {
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
  }

  public_subnet_tags = {
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
    "kubernetes.io/role/elb"                    = "1"
  }

  private_subnet_tags = {
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
    "kubernetes.io/role/internal-elb"           = "1"
  }
}

module "ray_eks_cluster" {
  # checkov:skip=CKV_AWS_355: Cluster Autoscaler requires wildcard Describe permissions; mutating permissions remain tag-scoped in the module.
  # checkov:skip=CKV_AWS_144: Velero backup replication is an opt-in cost tradeoff and is disabled by default in the module.
  # checkov:skip=CKV_AWS_18: Access logging for the optional Velero bucket is an opt-in cost tradeoff and is disabled by default in the module.
  # checkov:skip=CKV2_AWS_61: Lifecycle rules for the optional Velero bucket are workload-specific and intentionally left configurable.
  # checkov:skip=CKV2_AWS_62: Event notifications are not required for the optional Velero backup bucket.
  source = "../.."

  cluster_name = var.cluster_name
  region       = var.region

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  # For the example, keep sizes small to avoid excessive costs if applied
  cpu_node_min_size     = 1
  cpu_node_max_size     = 3
  cpu_node_desired_size = 1

  # Disable GPU nodes for a cheaper complete example
  enable_gpu_nodes = false
}
