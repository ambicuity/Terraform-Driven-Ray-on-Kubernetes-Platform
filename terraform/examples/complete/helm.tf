provider "helm" {
  kubernetes {
    host                   = module.ray_eks_cluster.cluster_endpoint
    cluster_ca_certificate = base64decode(module.ray_eks_cluster.cluster_certificate_authority)
    token                  = data.aws_eks_cluster_auth.cluster.token
  }
}

# Deploy the Kubernetes Cluster Autoscaler
resource "helm_release" "cluster_autoscaler" {
  name       = "cluster-autoscaler"
  repository = "https://kubernetes.github.io/autoscaler"
  chart      = "cluster-autoscaler"
  namespace  = "kube-system"
  version    = "9.32.0" # Example version for K8s 1.28 compatibility

  set {
    name  = "autoDiscovery.clusterName"
    value = var.cluster_name
  }

  set {
    name  = "awsRegion"
    value = var.region
  }

  set {
    name  = "rbac.serviceAccount.create"
    value = "true"
  }

  set {
    name  = "rbac.serviceAccount.name"
    value = "cluster-autoscaler"
  }

  set {
    name  = "rbac.serviceAccount.annotations.eks\\.amazonaws\\.com/role-arn"
    value = module.ray_eks_cluster.cluster_autoscaler_iam_role_arn
  }

  depends_on = [module.ray_eks_cluster]
}

# Deploy the KubeRay Operator
resource "helm_release" "kuberay_operator" {
  name             = "kuberay-operator"
  repository       = "https://ray-project.github.io/kuberay-helm/"
  chart            = "kuberay-operator"
  namespace        = "ray-system"
  create_namespace = true
  version          = "1.1.0"

  depends_on = [module.ray_eks_cluster]
}
