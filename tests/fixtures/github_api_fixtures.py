# MIT License
# Copyright (c) 2026 ambicuity
"""
Shared realistic GitHub API mock payloads for agent unit tests.

These payloads mirror the actual shape of GitHub REST API responses
to ensure tests catch real-world integration issues, not just type errors.
"""

from datetime import datetime, timezone

_NOW = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

# ---------------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------------

ISSUE_VALID = {
    "number": 42,
    "title": "EKS node group fails to provision on SPOT capacity — OOM on init container",
    "body": (
        "### Environment Info\n"
        "- OS: macOS 14.3\n"
        "- Terraform version: 1.7.4\n"
        "- EKS version: 1.31\n"
        "- KubeRay version: 2.9.0\n\n"
        "### Steps to Reproduce\n"
        "1. Apply the Terraform module with `gpu_capacity_type = \"SPOT\"`\n"
        "2. Wait for the node group to provision\n"
        "3. Run `kubectl get pods -n ray` and observe pods stuck in Init:OOMKilled\n\n"
        "### Expected vs Actual Output\n"
        "- Expected: Ray worker pods start successfully after node group provisions\n"
        "- Actual: Init container is OOMKilled. Memory limit appears to be 64Mi which "
        "is insufficient for the wait-gcs-ready check."
    ),
    "state": "open",
    "labels": [],
    "user": {"login": "contributor-alice", "id": 12345},
    "html_url": "https://github.com/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform/issues/42",
    "created_at": _NOW,
    "updated_at": _NOW,
}

ISSUE_MISSING_MARKERS = {
    "number": 43,
    "title": "Something is broken with the GPU nodes",
    "body": "I ran the apply and it doesn't work. Please help.",
    "state": "open",
    "labels": [],
    "user": {"login": "new-user-bob", "id": 99999},
    "html_url": "https://github.com/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform/issues/43",
    "created_at": _NOW,
    "updated_at": _NOW,
}

ISSUE_DUPLICATE_CANDIDATE = {
    "number": 41,
    "title": "EKS node group SPOT provisioning fails OOM init container",
    "body": "Node group provisioning is failing with OOM errors.",
    "state": "closed",
    "labels": [{"name": "bug"}, {"name": "infrastructure"}],
    "user": {"login": "old-reporter", "id": 11111},
    "html_url": "https://github.com/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform/issues/41",
    "created_at": _NOW,
    "updated_at": _NOW,
}

ISSUE_LOW_PRIORITY = {
    "number": 44,
    "title": "Typo in README.md — 'Kuberntes' should be 'Kubernetes'",
    "body": (
        "### Environment Info\n- N/A (documentation issue)\n\n"
        "### Steps to Reproduce\n1. Open README.md line 25\n2. See typo\n\n"
        "### Expected vs Actual Output\n"
        "- Expected: 'Kubernetes'\n- Actual: 'Kuberntes'"
    ),
    "state": "open",
    "labels": [],
    "user": {"login": "proofreader-carol", "id": 77777},
    "html_url": "https://github.com/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform/issues/44",
    "created_at": _NOW,
    "updated_at": _NOW,
}

# ---------------------------------------------------------------------------
# Pull Requests
# ---------------------------------------------------------------------------

PR_AI_GENERATED = {
    "number": 100,
    "title": "fix(ai-generated): EKS node group fails to provision on SPOT capacity (#42)",
    "body": (
        "## 🤖 AI-Generated Fix — Issue #42\n\n"
        "**Closes #42**\n\n"
        "### What this PR does\n"
        "Adjusts the init container memory limit from 64Mi to 256Mi to prevent OOMKilled.\n\n"
        "### Files Changed\n"
        "- `scripts/fix_issue_42.py`\n"
        "- `tests/test_issue_42.py`"
    ),
    "state": "open",
    "merged": False,
    "merged_at": None,
    "labels": [{"name": "ai-generated"}, {"name": "needs-review"}],
    "user": {"login": "github-actions[bot]", "id": 41898282},
    "head": {"ref": "ai-fix/42", "sha": "abc123def456"},
    "base": {"ref": "main"},
    "html_url": "https://github.com/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform/pull/100",
    "additions": 45,
    "deletions": 3,
    "changed_files": 2,
    "created_at": _NOW,
    "updated_at": _NOW,
}

PR_MERGED = {
    **PR_AI_GENERATED,
    "number": 100,
    "state": "closed",
    "merged": True,
    "merged_at": _NOW,
}

# Feature PR for SemVer bump testing
PR_FEATURE = {
    **PR_AI_GENERATED,
    "number": 101,
    "title": "feat(ai-generated): add S3 backup lifecycle policy (#45)",
    "labels": [{"name": "ai-generated"}, {"name": "enhancement"}],
    "merged": True,
    "merged_at": _NOW,
}

# ---------------------------------------------------------------------------
# Diffs
# ---------------------------------------------------------------------------

DIFF_CLEAN = """\
diff --git a/scripts/fix_issue_42.py b/scripts/fix_issue_42.py
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/scripts/fix_issue_42.py
@@ -0,0 +1,25 @@
+#!/usr/bin/env python3
+\"\"\"Fix for issue #42: increase init container memory limit.\"\"\"
+import os
+import json
+import sys
+
+
+def get_memory_limit(env: str = "production") -> str:
+    limits = {"production": "256Mi", "dev": "128Mi"}
+    return limits.get(env, "256Mi")
+
+
+def main() -> None:
+    env = os.environ.get("ENVIRONMENT", "production")
+    limit = get_memory_limit(env)
+    print(json.dumps({"memory_limit": limit}))
+
+
+if __name__ == "__main__":
+    main()
"""

DIFF_WITH_HALLUCINATION = """\
diff --git a/scripts/fix_issue_43.py b/scripts/fix_issue_43.py
new file mode 100644
index 0000000..abcdef0
--- /dev/null
+++ b/scripts/fix_issue_43.py
@@ -0,0 +1,10 @@
+#!/usr/bin/env python3
+import requests
+import boto3
+import numpy as np
+
+def fetch_data():
+    resp = requests.get("https://api.example.com/data")
+    return np.array(resp.json())
"""

# ---------------------------------------------------------------------------
# GitHub API generic responses
# ---------------------------------------------------------------------------

LABEL_CREATED = {
    "id": 12345678,
    "name": "status:triaged",
    "color": "bfd4f2",
    "description": "",
    "default": False,
}

COMMENT_CREATED = {
    "id": 987654321,
    "body": "Automated comment body",
    "user": {"login": "github-actions[bot]", "id": 41898282},
    "created_at": _NOW,
    "html_url": "https://github.com/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform/issues/42#issuecomment-987654321",
}

REF_CREATED = {
    "ref": "refs/heads/ai-fix/42",
    "object": {"sha": "abc123def456abc123def456", "type": "commit"},
}

MERGE_RESPONSE = {
    "sha": "deadbeefdeadbeefdeadbeef",
    "merged": True,
    "message": "Pull Request successfully merged",
}

CONTENTS_RESPONSE = {
    "content": {
        "name": "fix_issue_42.py",
        "path": "scripts/fix_issue_42.py",
        "sha": "newsha123",
        "size": 500,
        "html_url": "https://github.com/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform/blob/main/scripts/fix_issue_42.py",
    },
    "commit": {"sha": "commitsha789", "message": "fix(ai-fix/42): implement solution for issue #42"},
}

REPO_TREE = {
    "sha": "treesha123",
    "url": "https://api.github.com/repos/ambicuity/Terraform-Driven-Ray-on-Kubernetes-Platform/git/trees/treesha123",
    "tree": [
        {"path": "scripts/gamma_triage.py", "mode": "100644", "type": "blob", "sha": "a1", "size": 5000},
        {"path": "scripts/delta_executor.py", "mode": "100644", "type": "blob", "sha": "a2", "size": 4000},
        {"path": "terraform/main.tf", "mode": "100644", "type": "blob", "sha": "b1", "size": 8000},
        {"path": "policies/cost_governance.rego", "mode": "100644", "type": "blob", "sha": "c1", "size": 2000},
        {"path": ".github/workflows/gamma-triage.yml", "mode": "100644", "type": "blob", "sha": "d1", "size": 1000},
    ],
    "truncated": False,
}
