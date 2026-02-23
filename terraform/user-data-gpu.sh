#!/bin/bash
set -o xtrace

# Configure kubelet with GPU labels
/etc/eks/bootstrap.sh ${cluster_name} \
  --b64-cluster-ca ${cluster_ca} \
  --apiserver-endpoint ${cluster_endpoint} \
  --kubelet-extra-args '--node-labels=node.kubernetes.io/lifecycle=normal,ray.io/node-type=worker,nvidia.com/gpu=true'

# Install NVIDIA drivers
yum install -y gcc kernel-devel-$(uname -r)
aws s3 cp --recursive s3://ec2-linux-nvidia-drivers/latest/ .
chmod +x NVIDIA-Linux-x86_64*.run
./NVIDIA-Linux-x86_64*.run --silent

# Install NVIDIA container runtime
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.repo | \
  tee /etc/yum.repos.d/nvidia-docker.repo
yum install -y nvidia-container-toolkit
systemctl restart docker

# Verify GPU
nvidia-smi

# Set hostname
INSTANCE_ID=$(ec2-metadata --instance-id | cut -d " " -f 2)
hostnamectl set-hostname ${node_group_name}-$INSTANCE_ID
