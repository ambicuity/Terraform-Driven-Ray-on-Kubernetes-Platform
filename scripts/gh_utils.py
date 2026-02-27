#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 ambicuity
"""
gh_utils.py — Shared GitHub API + Gemini client for the Autonomous AI Agent Organization.

Centralises all urllib boilerplate so individual agent scripts never re-implement
HTTP request construction, JSON encoding, or retry logic. Eliminates the maintenance
risk of copy-pasted code and subtle header mismatches across agents.

Usage:
    from gh_utils import GithubClient, GeminiClient, append_internal_log, read_queue, write_queue

Security note:
    All write operations refuse to mutate anything under .github/workflows/ to prevent
    agents from escalating their own permissions or altering the CI/CD pipeline.
"""

import base64
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("gh_utils")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
QUEUE_PATH = ".ai_metadata/queue.json"
LOG_PATH = "INTERNAL_LOG.md"
# Model selection — matched to each agent's workload:
#   Pro  → Delta (code gen, up to 5 calls/issue) + Beta (security review)
#   Flash → Gamma (high-frequency triage) + Alpha (text synthesis, every 5 merges)
GEMINI_MODEL_PRO   = "gemini-2.5-pro"    # reasoning-critical: code gen and security review
GEMINI_MODEL_FLASH = "gemini-2.5-flash"  # fast, cost-efficient for triage / governance
GEMINI_MODEL       = GEMINI_MODEL_PRO     # default for any agent that does not override
_GEMINI_RETRY_DELAYS = [2, 5, 10]  # seconds with backoff for 429 / 503

# Files / path prefixes agents are NEVER allowed to write
_PROTECTED_PATH_PREFIXES = (".github/workflows/",)

# ---------------------------------------------------------------------------
# Allowed top-level Python imports in generated code
# Shared by Delta (code generation) and Beta (diff import scan).
# Both agents import this constant from here — single source of truth.
# ---------------------------------------------------------------------------
ALLOWED_IMPORTS = frozenset([
    "os", "sys", "re", "json", "time", "datetime", "subprocess", "pathlib",
    "urllib", "http", "io", "base64", "hashlib", "threading", "typing",
    "unittest", "collections", "itertools", "functools", "math", "logging",
    "argparse", "textwrap", "shutil", "tempfile", "contextlib", "dataclasses",
    "abc", "enum", "copy", "uuid", "random", "kubernetes", "yaml",
])


# ---------------------------------------------------------------------------
# GitHub Client
# ---------------------------------------------------------------------------

class GithubClient:
    """
    Thin authenticated wrapper over the GitHub REST API using stdlib urllib.
    All HTTP logic lives here — agents call semantic methods, not raw requests.
    """

    def __init__(self, token: str, repo: str) -> None:
        if not token:
            raise ValueError("GITHUB_TOKEN is required")
        if not repo or "/" not in repo:
            raise ValueError(f"GITHUB_REPOSITORY must be 'owner/repo', got: {repo!r}")
        self.token = token
        self.repo = repo
        self._base = f"https://api.github.com/repos/{repo}"

    # ------------------------------------------------------------------ #
    # Low-level primitives
    # ------------------------------------------------------------------ #

    def _request(
        self,
        url: str,
        *,
        method: str = "GET",
        payload: dict | None = None,
        accept: str = "application/vnd.github.v3+json",
    ) -> Any:
        """
        Execute an authenticated HTTP request. Returns the parsed JSON body,
        the raw response string (for diffs), or an empty dict on error.
        Raises on unrecoverable errors so callers can decide whether to abort.
        """
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"token {self.token}",
                "Accept": accept,
                "User-Agent": "autonomous-ai-agent",
                **({"Content-Type": "application/json"} if data else {}),
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                if accept.endswith("json"):
                    return json.loads(raw) if raw else {}
                return raw  # diff responses are plain text
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            logger.error("%s %s → HTTP %s: %s", method, url, exc.code, body[:200])
            if exc.code in (404, 409, 422):
                # Expected errors (not found, conflict, unprocessable) — return empty
                return {}
            raise  # let callers decide for unexpected errors

    def _delete(self, url: str) -> bool:
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"token {self.token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "autonomous-ai-agent",
            },
            method="DELETE",
        )
        try:
            urllib.request.urlopen(req)
            return True
        except urllib.error.HTTPError as exc:
            logger.warning("DELETE %s → %s", url, exc.code)
            return False

    # ------------------------------------------------------------------ #
    # Issues
    # ------------------------------------------------------------------ #

    def get_issue(self, number: int) -> dict:
        return self._request(f"{self._base}/issues/{number}")  # type: ignore[return-value]

    def post_comment(self, number: int, body: str) -> dict:
        return self._request(
            f"{self._base}/issues/{number}/comments",
            method="POST",
            payload={"body": body},
        )  # type: ignore[return-value]

    def ensure_label(self, name: str, color: str = "ededed") -> None:
        """Create the label if absent (ignores 422 Unprocessable = already exists)."""
        self._request(
            f"{self._base}/labels",
            method="POST",
            payload={"name": name, "color": color},
        )

    def add_labels(self, number: int, labels: list[str]) -> None:
        self._request(
            f"{self._base}/issues/{number}/labels",
            method="POST",
            payload={"labels": labels},
        )

    def remove_label(self, number: int, label: str) -> bool:
        """Remove a label from an issue/PR. Returns False if label was not present."""
        encoded = urllib.parse.quote(label, safe="")
        result = self._delete(f"{self._base}/issues/{number}/labels/{encoded}")
        return result

    def claim_issue(self, number: int) -> bool:
        """
        Atomically claim an issue for Agent Delta by swapping
        'status:triaged' → 'status:in-progress'.

        Returns True only if the swap succeeded (i.e., this instance won the race).
        If another concurrent Delta already removed 'status:triaged', returns False
        so the caller can exit gracefully without doing duplicate work.
        """
        self.ensure_label("status:in-progress", "0075ca")
        self.add_labels(number, ["status:in-progress"])
        removed = self.remove_label(number, "status:triaged")
        if not removed:
            logger.warning(
                "Could not remove 'status:triaged' from issue #%s — "
                "another Delta instance likely claimed it first. Exiting.",
                number,
            )
        return removed

    def list_issues(self, state: str = "closed", per_page: int = 10) -> list:
        result = self._request(
            f"{self._base}/issues?state={state}&per_page={per_page}&sort=updated"
        )
        return result if isinstance(result, list) else []

    # ------------------------------------------------------------------ #
    # Pull Requests
    # ------------------------------------------------------------------ #

    def get_pr_diff(self, pr_number: int, max_chars: int = 50_000) -> str:
        diff = self._request(
            f"{self._base}/pulls/{pr_number}",
            accept="application/vnd.github.v3.diff",
        )
        if isinstance(diff, str):
            return diff[:max_chars]
        return ""

    def get_pr(self, pr_number: int) -> dict:
        return self._request(f"{self._base}/pulls/{pr_number}")  # type: ignore[return-value]

    def create_pr(self, head: str, title: str, body: str) -> dict:
        return self._request(
            f"{self._base}/pulls",
            method="POST",
            payload={"title": title, "head": head, "base": "main", "body": body, "draft": False},
        )  # type: ignore[return-value]

    def merge_pr(self, pr_number: int) -> bool:
        result = self._request(
            f"{self._base}/pulls/{pr_number}/merge",
            method="PUT",
            payload={"merge_method": "squash"},
        )
        return bool(result.get("merged")) if isinstance(result, dict) else False

    def list_merged_prs(self, count: int = 5) -> list:
        pulls = self._request(
            f"{self._base}/pulls?state=closed&sort=updated&direction=desc&per_page={count * 2}"
        )
        if not isinstance(pulls, list):
            return []
        return [p for p in pulls if p.get("merged_at")][:count]

    # ------------------------------------------------------------------ #
    # Branches and Refs
    # ------------------------------------------------------------------ #

    def get_main_sha(self) -> str:
        data = self._request(f"{self._base}/git/ref/heads/main")
        return data.get("object", {}).get("sha", "") if isinstance(data, dict) else ""

    def create_branch(self, name: str, sha: str) -> bool:
        result = self._request(
            f"{self._base}/git/refs",
            method="POST",
            payload={"ref": f"refs/heads/{name}", "sha": sha},
        )
        return bool(result.get("ref")) if isinstance(result, dict) else False

    def delete_branch(self, name: str) -> bool:
        encoded = urllib.parse.quote(name, safe="")
        return self._delete(f"{self._base}/git/refs/heads/{encoded}")

    def list_branches(self, prefix: str = "") -> list[str]:
        branches = self._request(f"{self._base}/branches?per_page=100")
        if not isinstance(branches, list):
            return []
        return [b["name"] for b in branches if b.get("name", "").startswith(prefix)]

    def create_tag(self, tag: str, sha: str) -> bool:
        result = self._request(
            f"{self._base}/git/refs",
            method="POST",
            payload={"ref": f"refs/tags/{tag}", "sha": sha},
        )
        return bool(result.get("ref")) if isinstance(result, dict) else False

    # ------------------------------------------------------------------ #
    # File contents (Contents API)
    # ------------------------------------------------------------------ #

    @staticmethod
    def _guard_protected_path(path: str) -> None:
        """
        Hard-block any write to protected paths.
        Agents must NEVER be able to modify their own CI/CD workflows.
        """
        for prefix in _PROTECTED_PATH_PREFIXES:
            if path.startswith(prefix):
                raise PermissionError(
                    f"Security guard: agents cannot write to protected path '{path}'. "
                    f"Protected prefixes: {_PROTECTED_PATH_PREFIXES}"
                )

    def read_file(self, path: str, ref: str = "main") -> tuple[str, str]:
        """Returns (decoded_content, sha). Returns ('', '') on 404."""
        data = self._request(f"{self._base}/contents/{path}?ref={ref}")
        if not isinstance(data, dict) or "content" not in data:
            return "", ""
        content = base64.b64decode(data["content"]).decode("utf-8")
        return content, data.get("sha", "")

    def write_file(self, path: str, content: str, sha: str, message: str, branch: str = "main") -> bool:
        """
        Create or update a file via the Contents API.
        Protected paths are rejected before any network call is made.
        """
        self._guard_protected_path(path)
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        payload: dict = {"message": message, "content": encoded, "branch": branch}
        if sha:
            payload["sha"] = sha
        result = self._request(f"{self._base}/contents/{path}", method="PUT", payload=payload)
        return bool(result.get("content")) if isinstance(result, dict) else False

    def get_repo_tree(self, max_paths: int = 200) -> str:
        """Returns a newline-joined list of relevant file paths for context injection."""
        data = self._request(f"{self._base}/git/trees/main?recursive=1")
        if not isinstance(data, dict):
            return ""
        exts = {".tf", ".py", ".rego", ".yml", ".yaml", ".md", ".json", ".hcl"}
        paths = [
            item["path"] for item in data.get("tree", [])
            if item["type"] == "blob" and os.path.splitext(item["path"])[1].lower() in exts
        ]
        return "\n".join(sorted(paths)[:max_paths])

    # ------------------------------------------------------------------ #
    # Dispatches
    # ------------------------------------------------------------------ #

    def trigger_dispatch(self, event_type: str) -> None:
        self._request(
            f"{self._base}/dispatches",
            method="POST",
            payload={"event_type": event_type},
        )

    # ------------------------------------------------------------------ #
    # Persistent state — queue.json and INTERNAL_LOG.md via Contents API
    # ------------------------------------------------------------------ #
    # GitHub Actions runners are EPHEMERAL. Any local file write is lost
    # when the job exits. All state that must survive across job boundaries
    # (queue.json, INTERNAL_LOG.md) MUST be committed via the Contents API.

    def read_queue(self) -> dict:
        """Read .ai_metadata/queue.json from the repo via Contents API."""
        content, _ = self.read_file(QUEUE_PATH)
        if not content:
            return {
                "schema_version": "1.0",
                "queued": [],
                "in_progress": None,
                "merge_count": 0,
                "last_governance_merge": 0,
            }
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            logger.error("Corrupt queue.json — returning empty state.")
            return {
                "schema_version": "1.0",
                "queued": [],
                "in_progress": None,
                "merge_count": 0,
                "last_governance_merge": 0,
            }

    def write_queue(self, queue: dict) -> bool:
        """
        Write .ai_metadata/queue.json to the repo via the Contents API.

        Conflict handling (409 / sha mismatch):
          If another agent committed a change between this agent's read and write,
          the Contents API returns 409 Conflict. _request() converts that to an
          empty dict, making write_file() return False.
          On failure, we re-read the file to get the current sha and retry once.
          The queue dict being written is unchanged — it contains this agent's
          intended state. The caller is responsible for merging logic if needed.
        """
        content = json.dumps(queue, indent=2) + "\n"
        _, sha = self.read_file(QUEUE_PATH)
        ok = self.write_file(
            QUEUE_PATH, content, sha,
            "chore(agent-state): update queue.json [skip ci]"
        )
        if ok:
            return True
        # Retry once — 409 caused by a concurrent agent write between our read and PUT.
        logger.warning(
            "write_queue: write failed (likely 409 sha conflict) — "
            "re-fetching sha and retrying once."
        )
        _, fresh_sha = self.read_file(QUEUE_PATH)
        return self.write_file(
            QUEUE_PATH, content, fresh_sha,
            "chore(agent-state): update queue.json [skip ci]"
        )

    def append_log(self, agent: str, issue_or_pr: str, action: str, state: str, notes: str) -> bool:
        """
        Append a structured entry to INTERNAL_LOG.md via the Contents API.

        Conflict handling (409 / sha mismatch):
          If another agent committed to INTERNAL_LOG.md between our read and write,
          we re-read the current file content (to capture their entry too) and
          append our entry on top of the refreshed content, then retry once.
          This ensures no log entry is silently dropped.
        """
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        entry = (
            f"\n## Agent {agent} — {ts}\n"
            f"- **Issue/PR**: {issue_or_pr}\n"
            f"- **Action**: {action}\n"
            f"- **State**: {state}\n"
            f"- **Notes**: {notes}\n"
        )
        existing, sha = self.read_file(LOG_PATH)
        ok = self.write_file(
            LOG_PATH,
            (existing or "") + entry,
            sha,
            f"chore(agent-log): {agent} — {action[:60]} [skip ci]"
        )
        if ok:
            return True
        # Retry once — re-read so we don't clobber a concurrent agent's log entry.
        logger.warning(
            "append_log: write failed (likely 409 sha conflict) — "
            "re-fetching content+sha and retrying once."
        )
        fresh_existing, fresh_sha = self.read_file(LOG_PATH)
        return self.write_file(
            LOG_PATH,
            (fresh_existing or "") + entry,
            fresh_sha,
            f"chore(agent-log): {agent} — {action[:60]} [skip ci]"
        )


# ---------------------------------------------------------------------------
# Gemini Client
# ---------------------------------------------------------------------------

class GeminiClient:
    """
    Wraps the Gemini REST API (v1beta) with production-grade hardening:

      - API key sent via 'x-goog-api-key' header (not URL query param) to
        prevent key exposure in server-side access logs.
      - Thinking mode explicitly disabled (thinkingBudget=0) for gemini-2.5
        models which enable thinking by default, causing silent latency/cost
        spikes in high-volume agentic workflows.
      - Respects the 'Retry-After' header on 429 responses instead of using
        hardcoded delays that may under- or over-wait.
      - Checks Candidate.finishReason and promptFeedback.blockReason so that
        safety blocks and RECITATION stops are logged explicitly rather than
        silently returning an empty string.
    """

    def __init__(self, api_key: str, model: str = GEMINI_MODEL) -> None:
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required")
        self.api_key = api_key
        self.model = model
        # API key goes in the header, NOT the URL, to avoid leaking it into
        # server-side access logs and request traces.
        self._url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent"
        )
        self._headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        }

    def generate(
        self,
        prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        system_instruction: str = "",
    ) -> str:
        """
        Send a prompt to Gemini; returns the text response or empty string on
        failure. All failures are logged with a reason so silent empty returns
        are traceable in the CI job log.
        """
        # Choose thinking budget based on model tier:
        #   Pro (code gen, security review): allow up to 8192 thinking tokens for
        #     deeper reasoning — the latency trade-off is acceptable for these tasks.
        #   Flash (triage, governance text synthesis): keep at 0 for speed.
        thinking_budget = 8192 if self.model == GEMINI_MODEL_PRO else 0
        payload: dict = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "thinkingConfig": {"thinkingBudget": thinking_budget},
            },
        }
        if system_instruction:
            payload["system_instruction"] = {"parts": [{"text": system_instruction}]}

        for attempt, default_delay in enumerate(_GEMINI_RETRY_DELAYS + [None]):
            req = urllib.request.Request(
                self._url,
                data=json.dumps(payload).encode("utf-8"),
                headers=self._headers,
                method="POST",
            )
            try:
                with urllib.request.urlopen(req) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                    return self._extract_text(result)
            except urllib.error.HTTPError as exc:
                if exc.code in (429, 500, 503) and default_delay is not None:
                    # Honour Retry-After if the server provides it, otherwise
                    # fall back to our own backoff schedule.
                    retry_after = exc.headers.get("Retry-After")
                    wait = int(retry_after) if retry_after and retry_after.isdigit() else default_delay
                    logger.warning(
                        "Gemini HTTP %s — retrying in %ss (attempt %s/%s)...",
                        exc.code, wait, attempt + 1, len(_GEMINI_RETRY_DELAYS)
                    )
                    time.sleep(wait)
                    continue
                logger.error(
                    "Gemini API unrecoverable error %s: %s",
                    exc.code,
                    exc.read().decode("utf-8", errors="replace")[:200]
                )
                return ""
        logger.error("Gemini API: exhausted all %s retry attempts.", len(_GEMINI_RETRY_DELAYS))
        return ""

    @staticmethod
    def _extract_text(result: dict) -> str:
        """
        Parse a GenerateContentResponse dict and return the text output.

        Checks both promptFeedback.blockReason (prompt blocked before candidates
        are generated) and Candidate.finishReason (response truncated by safety
        or recitation) so callers get explicit log lines instead of silent ''.
        """
        # Prompt-level block (e.g. prompt itself triggered safety filter)
        prompt_feedback = result.get("promptFeedback", {})
        block_reason = prompt_feedback.get("blockReason")
        if block_reason:
            logger.warning("Gemini prompt blocked — blockReason: %s", block_reason)
            return ""

        candidates = result.get("candidates", [])
        if not candidates:
            logger.warning("Gemini returned no candidates.")
            return ""

        candidate = candidates[0]
        finish_reason = candidate.get("finishReason", "STOP")
        if finish_reason not in ("STOP", "MAX_TOKENS", "", None):
            # SAFETY, RECITATION, OTHER — content field will be absent or empty
            logger.warning("Gemini candidate finish_reason=%s — returning empty.", finish_reason)
            return ""

        parts = candidate.get("content", {}).get("parts", [])
        if not parts:
            logger.warning("Gemini candidate has no content parts (finish_reason=%s).", finish_reason)
            return ""

        return parts[0].get("text", "")


# ---------------------------------------------------------------------------
# Code Sandbox — py_compile check
# ---------------------------------------------------------------------------

def compile_check(code: str) -> tuple[bool, str]:
    """
    Write generated Python code to a temp file and run py_compile on it.
    Returns (passed: bool, error_message: str).
    This catches syntax errors and invalid references that a regex import scan cannot.
    """
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(code)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", tmp_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return True, ""
        error = result.stderr.replace(tmp_path, "<generated>").strip()
        return False, error
    except subprocess.TimeoutExpired:
        return False, "py_compile timed out"
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Queue management
# ---------------------------------------------------------------------------

def read_queue() -> dict:
    try:
        with open(QUEUE_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "schema_version": "1.0",
            "queued": [],
            "in_progress": None,
            "merge_count": 0,
            "last_governance_merge": 0,
        }


def write_queue(queue: dict) -> None:
    os.makedirs(os.path.dirname(QUEUE_PATH), exist_ok=True)
    with open(QUEUE_PATH, "w", encoding="utf-8") as fh:
        json.dump(queue, fh, indent=2)
        fh.write("\n")


# ---------------------------------------------------------------------------
# INTERNAL_LOG
# ---------------------------------------------------------------------------

def append_internal_log(agent: str, issue_or_pr: str, action: str, state: str, notes: str) -> None:
    """
    Append a structured entry to INTERNAL_LOG.md.
    Called by all agents to maintain bus-factor continuity.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = (
        f"\n## Agent {agent} — {ts}\n"
        f"- **Issue/PR**: {issue_or_pr}\n"
        f"- **Action**: {action}\n"
        f"- **State**: {state}\n"
        f"- **Notes**: {notes}\n"
    )
    with open(LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write(entry)


# ---------------------------------------------------------------------------
# Environment validation helper
# ---------------------------------------------------------------------------

def require_env(*names: str) -> dict[str, str]:
    """
    Validate that all required environment variable names are set.
    Exits with a clear error message if any are missing.
    Returns a dict of {name: value}.
    """
    values: dict[str, str] = {}
    missing = []
    for name in names:
        val = os.environ.get(name, "")
        if not val:
            missing.append(name)
        else:
            values[name] = val
    if missing:
        logger.error("Missing required environment variables: %s", ", ".join(missing))
        sys.exit(1)
    return values
