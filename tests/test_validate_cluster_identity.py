#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 ambicuity
"""
Unit tests for validate_cluster_identity.py — kubeconfig validation and cluster fingerprinting.

Tests cover:
  - check_kubeconfig_exists: handles missing files, KUBECONFIG env var, default path
  - get_cluster_fingerprint: returns proper error messages for missing kubeconfig
"""

import sys
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import validate_cluster_identity  # noqa: E402


class TestCheckKubeconfigExists(unittest.TestCase):
    """Tests for check_kubeconfig_exists function."""

    def test_returns_path_when_default_config_exists(self):
        """When ~/.kube/config exists, return its path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            kube_dir = os.path.join(tmpdir, ".kube")
            os.makedirs(kube_dir)
            config_path = os.path.join(kube_dir, "config")
            with open(config_path, "w") as f:
                f.write("# test config")

            with patch.dict(os.environ, {"HOME": tmpdir}, clear=False):
                with patch.dict(os.environ, {}, clear=False):
                    # Ensure KUBECONFIG is not set
                    if "KUBECONFIG" in os.environ:
                        del os.environ["KUBECONFIG"]
                    result = validate_cluster_identity.check_kubeconfig_exists()

            self.assertEqual(result, config_path)

    def test_returns_none_and_path_when_default_config_missing(self):
        """When ~/.kube/config doesn't exist, return (None, expected_path)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"HOME": tmpdir}, clear=False):
                with patch.dict(os.environ, {}, clear=False):
                    if "KUBECONFIG" in os.environ:
                        del os.environ["KUBECONFIG"]
                    result = validate_cluster_identity.check_kubeconfig_exists()

            self.assertIsInstance(result, tuple)
            self.assertIsNone(result[0])
            self.assertEqual(result[1], os.path.join(tmpdir, ".kube", "config"))

    def test_respects_kubeconfig_env_var(self):
        """When KUBECONFIG is set and file exists, use that path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            custom_config = os.path.join(tmpdir, "my-cluster.yaml")
            with open(custom_config, "w") as f:
                f.write("# custom config")

            with patch.dict(os.environ, {"KUBECONFIG": custom_config}):
                result = validate_cluster_identity.check_kubeconfig_exists()

            self.assertEqual(result, custom_config)

    def test_kubeconfig_env_var_missing_file(self):
        """When KUBECONFIG points to non-existent file, return (None, path)."""
        missing_path = "/tmp/nonexistent/config.yaml"
        with patch.dict(os.environ, {"KUBECONFIG": missing_path}):
            result = validate_cluster_identity.check_kubeconfig_exists()

        self.assertIsInstance(result, tuple)
        self.assertIsNone(result[0])
        self.assertEqual(result[1], missing_path)

    def test_kubeconfig_colon_separated_paths(self):
        """KUBECONFIG can contain multiple colon-separated paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config1 = os.path.join(tmpdir, "config1.yaml")
            config2 = os.path.join(tmpdir, "config2.yaml")

            # Only config2 exists
            with open(config2, "w") as f:
                f.write("# config2")

            with patch.dict(os.environ, {"KUBECONFIG": f"{config1}:{config2}"}):
                result = validate_cluster_identity.check_kubeconfig_exists()

            # Should return the first existing file
            self.assertEqual(result, config2)

    def test_kubeconfig_colon_separated_all_missing(self):
        """When KUBECONFIG has multiple paths but all missing, return first."""
        missing1 = "/tmp/missing1.yaml"
        missing2 = "/tmp/missing2.yaml"

        with patch.dict(os.environ, {"KUBECONFIG": f"{missing1}:{missing2}"}):
            result = validate_cluster_identity.check_kubeconfig_exists()

        self.assertIsInstance(result, tuple)
        self.assertIsNone(result[0])
        self.assertEqual(result[1], missing1)


class TestGetClusterFingerprintErrors(unittest.TestCase):
    """Tests for get_cluster_fingerprint error handling."""

    def test_missing_kubeconfig_returns_error_status(self):
        """Missing kubeconfig should return error status with helpful message."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"HOME": tmpdir}, clear=False):
                with patch.dict(os.environ, {}, clear=False):
                    if "KUBECONFIG" in os.environ:
                        del os.environ["KUBECONFIG"]
                    result = validate_cluster_identity.get_cluster_fingerprint()

        self.assertEqual(result["status"], "error")
        self.assertIn("Kubeconfig file not found", result["message"])
        self.assertIn(".kube/config", result["message"])
        self.assertIn("aws eks update-kubeconfig", result["message"])

    def test_missing_kubeconfig_env_var_returns_error(self):
        """Missing kubeconfig via KUBECONFIG env var returns clear error."""
        missing_path = "/tmp/test_missing/kubeconfig.yaml"
        with patch.dict(os.environ, {"KUBECONFIG": missing_path}):
            result = validate_cluster_identity.get_cluster_fingerprint()

        self.assertEqual(result["status"], "error")
        self.assertIn("Kubeconfig file not found", result["message"])
        self.assertIn(missing_path, result["message"])

    @patch("validate_cluster_identity.subprocess.run")
    def test_kubectl_not_found_returns_error(self, mock_run):
        """When kubectl is not installed, return appropriate error."""
        # Create a valid kubeconfig
        with tempfile.TemporaryDirectory() as tmpdir:
            kube_dir = os.path.join(tmpdir, ".kube")
            os.makedirs(kube_dir)
            config_path = os.path.join(kube_dir, "config")
            with open(config_path, "w") as f:
                f.write("# test config")

            # Mock kubectl not found
            mock_run.side_effect = FileNotFoundError("kubectl")

            with patch.dict(os.environ, {"HOME": tmpdir}, clear=False):
                with patch.dict(os.environ, {}, clear=False):
                    if "KUBECONFIG" in os.environ:
                        del os.environ["KUBECONFIG"]
                    result = validate_cluster_identity.get_cluster_fingerprint()

        self.assertEqual(result["status"], "error")
        self.assertIn("kubectl not found in PATH", result["message"])


class TestMainExitCodes(unittest.TestCase):
    """Tests for main() function exit codes."""

    @patch("validate_cluster_identity.get_cluster_fingerprint")
    def test_missing_kubeconfig_exits_with_code_1(self, mock_fingerprint):
        """Main should exit with code 1 when kubeconfig is missing."""
        mock_fingerprint.return_value = {
            "status": "error",
            "message": "Kubeconfig file not found at: /tmp/test/.kube/config\n"
                      "Please ensure your Kubernetes configuration is set up correctly.\n"
                      "You may need to run: aws eks update-kubeconfig --name <cluster-name> --region <region>"
        }

        with self.assertRaises(SystemExit) as cm:
            validate_cluster_identity.main()

        self.assertEqual(cm.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
