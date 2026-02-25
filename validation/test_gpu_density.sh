#!/usr/bin/env bash
# MIT License
# Copyright (c) 2026 ambicuity
# Tests the GPU Pod Density enabled by AWS VPC CNI Prefix Delegation.

set -eo pipefail

echo "🚀 Validating GPU Node Pod Density (Prefix Delegation)"

# Find all g4dn.xlarge (or similar GPU nodes)
NODES=$(kubectl get nodes -l node.kubernetes.io/instance-type=g4dn.xlarge -o jsonpath='{.items[*].metadata.name}')

if [ -z "$NODES" ]; then
    echo "⚠️ No g4dn.xlarge nodes found in the cluster."
    echo "To test this locally, ensure the GPU node pool has scaled up an instance."
    echo "Run: kubectl get nodes --show-labels"
    exit 1
fi

SUCCESS_COUNT=0
for NODE in $NODES; do
    echo "--------------------------------------------------"
    echo "📊 Inspecting node: $NODE"
    
    CAPACITY=$(kubectl get node "$NODE" -o jsonpath='{.status.capacity.pods}')
    echo "Maximum Pod Capacity (Allocatable): $CAPACITY"
    
    # Explain the math
    echo "Standard ENI IP Limit for g4dn.xlarge is ~14 pods."
    
    if [ "$CAPACITY" -lt 50 ]; then
        echo "❌ FAILED: Node capacity is $CAPACITY. Prefix Delegation is NOT enabled."
        exit 1
    else
        echo "✅ SUCCESS: Node capacity is $CAPACITY (>14). Prefix delegation is mathematically verified!"
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    fi
done

echo "--------------------------------------------------"
echo "✅ Test completed: $SUCCESS_COUNT nodes verified for high-density networking."
