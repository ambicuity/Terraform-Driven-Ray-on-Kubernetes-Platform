provider "aws" {
  region = var.region
}

data "aws_eks_cluster_auth" "cluster" {
  name = module.ray_eks_cluster.cluster_name
}

provider "kubernetes" {
  host                   = module.ray_eks_cluster.cluster_endpoint
  cluster_ca_certificate = base64decode(module.ray_eks_cluster.cluster_certificate_authority_data)
  token                  = data.aws_eks_cluster_auth.cluster.token
}

module "ray_eks_cluster" {
  source = "../.."

  cluster_name = var.cluster_name
  region       = var.region
  vpc_cidr     = var.vpc_cidr

  # For the example, keep sizes small to avoid excessive costs if applied
  cpu_node_min_size     = 1
  cpu_node_max_size     = 3
  cpu_node_desired_size = 1

  # Disable GPU nodes for a cheaper complete example
  enable_gpu_nodes = false
}
