#!/bin/bash
set -o xtrace

# Configure kubelet
/etc/eks/bootstrap.sh ${cluster_name} \
  --b64-cluster-ca ${cluster_ca} \
  --apiserver-endpoint ${cluster_endpoint} \
  --kubelet-extra-args '--node-labels=node.kubernetes.io/lifecycle=normal,ray.io/node-type=worker'

# Install CloudWatch agent (optional)
wget https://s3.amazonaws.com/amazoncloudwatch-agent/amazon_linux/amd64/latest/amazon-cloudwatch-agent.rpm
rpm -U ./amazon-cloudwatch-agent.rpm

# Set hostname
INSTANCE_ID=$(ec2-metadata --instance-id | cut -d " " -f 2)
hostnamectl set-hostname ${node_group_name}-$INSTANCE_ID
