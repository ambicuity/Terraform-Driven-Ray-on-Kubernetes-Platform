#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 ambicuity
"""
Unit tests for Agent Delta (delta_executor.py) — post-refactor.

Tests cover:
  - Queue selection and label-claim guard
  - Import extraction from generated code
  - Two-stage preflight: import whitelist + py_compile + Gemini
"""

import sys
import os
import unittest
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import delta_executor  # noqa: E402


class TestQueueSelection(unittest.TestCase):

    def test_returns_none_for_empty_queue(self):
        result = delta_executor.select_issue({"queued": [], "in_progress": None}, "999")
        self.assertIsNone(result)

    def test_returns_matched_issue_by_number(self):
        queue = {
            "queued": [
                {"issue_number": 10, "priority": "high"},
                {"issue_number": 42, "priority": "medium"},
            ],
            "in_progress": None,
        }
        result = delta_executor.select_issue(queue, "42")
        self.assertEqual(result["issue_number"], 42)

    def test_returns_first_item_when_no_exact_match(self):
        queue = {
            "queued": [
                {"issue_number": 10, "priority": "high"},
                {"issue_number": 20, "priority": "low"},
            ],
            "in_progress": None,
        }
        result = delta_executor.select_issue(queue, "999")
        self.assertEqual(result["issue_number"], 10)


class TestImportExtraction(unittest.TestCase):

    def test_extracts_simple_import(self):
        code = "import os\nimport sys\n"
        self.assertIn("os", delta_executor.extract_imports(code))
        self.assertIn("sys", delta_executor.extract_imports(code))

    def test_extracts_from_import(self):
        code = "from json import dumps\nfrom urllib.request import urlopen\n"
        imports = delta_executor.extract_imports(code)
        self.assertIn("json", imports)
        self.assertIn("urllib", imports)

    def test_detects_third_party_imports(self):
        code = "import requests\nfrom boto3 import client\n"
        imports = delta_executor.extract_imports(code)
        self.assertIn("requests", imports)
        self.assertIn("boto3", imports)

    def test_clean_stdlib_code_no_hallucinations(self):
        code = "import os\nimport json\nimport re\n"
        hallucinated = delta_executor.extract_imports(code) - delta_executor.ALLOWED_IMPORTS
        self.assertEqual(hallucinated, set())


class TestPreflightCheck(unittest.TestCase):

    def test_hallucinated_import_blocked_before_compile(self):
        """Hallucinated import should short-circuit before py_compile or Gemini."""
        code = "import pandas as pd\ndef main(): df = pd.DataFrame()\n"
        mock_gemini = MagicMock()
        with patch("delta_executor.compile_check") as mock_compile:
            passed, feedback = delta_executor.preflight(code, mock_gemini)
        mock_compile.assert_not_called()
        mock_gemini.generate.assert_not_called()
        self.assertFalse(passed)
        self.assertIn("pandas", feedback)

    def test_compile_error_blocked_before_gemini(self):
        """py_compile failure should block before Gemini is called."""
        code = "import os\ndef broken(:\n"  # Intentional syntax error
        mock_gemini = MagicMock()
        with patch("delta_executor.compile_check", return_value=(False, "SyntaxError: invalid syntax")):
            passed, feedback = delta_executor.preflight(code, mock_gemini)
        mock_gemini.generate.assert_not_called()
        self.assertFalse(passed)
        self.assertIn("Compile error", feedback)

    def test_gemini_approved_passes(self):
        code = "import os\n\ndef main():\n    print(os.getcwd())\n"
        mock_gemini = MagicMock()
        mock_gemini.generate.return_value = "APPROVED\nCode is clean."
        with patch("delta_executor.compile_check", return_value=(True, "")):
            passed, _ = delta_executor.preflight(code, mock_gemini)
        self.assertTrue(passed)

    def test_gemini_rejected_fails(self):
        code = "import os\ndef main(): pass\n"
        mock_gemini = MagicMock()
        mock_gemini.generate.return_value = "REJECTED\n- No docstring\n- Missing error handling"
        with patch("delta_executor.compile_check", return_value=(True, "")):
            passed, feedback = delta_executor.preflight(code, mock_gemini)
        self.assertFalse(passed)
        self.assertIn("REJECTED", feedback)

    def test_empty_gemini_response_fails_gracefully(self):
        code = "import os\ndef main(): pass\n"
        mock_gemini = MagicMock()
        mock_gemini.generate.return_value = ""
        with patch("delta_executor.compile_check", return_value=(True, "")):
            passed, _ = delta_executor.preflight(code, mock_gemini)
        self.assertFalse(passed)


if __name__ == "__main__":
    unittest.main()
