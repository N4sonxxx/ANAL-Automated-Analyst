"""
linter_runner.py — Static Analysis Runner
Runs the appropriate linter based on detected language.
Fails silently if linter is not installed — never crashes the pipeline.
"""

import subprocess
import json


def run(project_path: str, profile: dict) -> str:
    """
    Run a language-appropriate static analysis linter.
    Returns a human-readable string of the top issues.
    Returns a graceful message if no linter is available.
    """
    language = profile.get("language", "Unknown")
    print(f"  [Linter] Running static analysis for: {language}")

    if language == "Python":
        return _run_python_linter(project_path)
    elif language in ("JavaScript/TypeScript",):
        return _run_eslint(project_path)
    else:
        return f"Linter not configured for {language}. Skipping static analysis."


def _run_python_linter(project_path: str) -> str:
    """Try ruff first, fall back to pylint, then give up gracefully."""

    # ── Try ruff (faster, modern) ────────────────────────────────────────────
    try:
        result = subprocess.run(
            ["ruff", "check", project_path, "--output-format", "json", "--no-cache"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        raw = result.stdout.strip() or result.stderr.strip()
        if raw:
            try:
                issues = json.loads(raw)
                return _format_ruff_output(issues)
            except json.JSONDecodeError:
                return f"Ruff output:\n{raw[:3000]}"
    except FileNotFoundError:
        pass  # ruff not installed, try pylint
    except subprocess.TimeoutExpired:
        return "Linter timed out after 30 seconds."

    # ── Try pylint ────────────────────────────────────────────────────────────
    try:
        result = subprocess.run(
            ["pylint", project_path,
             "--output-format=json",
             "--disable=C0114,C0115,C0116",   # Ignore missing docstrings
             "--recursive=y"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        raw = result.stdout.strip()
        if raw:
            try:
                issues = json.loads(raw)
                return _format_pylint_output(issues)
            except json.JSONDecodeError:
                return f"Pylint output:\n{raw[:3000]}"
    except FileNotFoundError:
        pass
    except subprocess.TimeoutExpired:
        return "Pylint timed out after 60 seconds."

    return "No Python linter found (ruff or pylint). Install with: pip install ruff"


def _run_eslint(project_path: str) -> str:
    """Run ESLint for JavaScript/TypeScript projects."""
    try:
        result = subprocess.run(
            ["npx", "eslint", project_path, "--format", "json", "--max-warnings", "50"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=project_path,
        )
        raw = result.stdout.strip()
        if raw:
            try:
                data = json.loads(raw)
                return _format_eslint_output(data)
            except json.JSONDecodeError:
                return f"ESLint output:\n{raw[:3000]}"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return "ESLint not available. Skipping static analysis."


# ── Formatters ────────────────────────────────────────────────────────────────

def _format_ruff_output(issues: list) -> str:
    if not issues:
        return "Ruff: No issues found. ✅"

    # Severity mapping: ruff uses codes
    SEVERITY_ORDER = {"E": 0, "W": 1, "F": 2, "C": 3, "N": 4, "I": 5, "B": 6}

    def severity_key(issue):
        code = issue.get("code", "Z")
        return SEVERITY_ORDER.get(code[0], 9) if code else 9

    top_issues = sorted(issues, key=severity_key)[:25]
    lines = [f"Ruff Static Analysis — {len(issues)} issues found (showing top {len(top_issues)}):"]
    for issue in top_issues:
        loc = issue.get("location", {})
        path = issue.get("filename", "?")
        row = loc.get("row", "?")
        code = issue.get("code", "?")
        msg = issue.get("message", "?")
        lines.append(f"  [{code}] {path}:{row} — {msg}")
    return "\n".join(lines)


def _format_pylint_output(issues: list) -> str:
    if not issues:
        return "Pylint: No issues found. ✅"

    SEVERITY_ORDER = {"error": 0, "warning": 1, "refactor": 2, "convention": 3}
    top_issues = sorted(issues, key=lambda x: SEVERITY_ORDER.get(x.get("type", "z"), 9))[:25]
    lines = [f"Pylint Static Analysis — {len(issues)} issues found (showing top {len(top_issues)}):"]
    for issue in top_issues:
        severity = issue.get("type", "?").upper()
        path = issue.get("path", "?")
        line = issue.get("line", "?")
        symbol = issue.get("symbol", "?")
        msg = issue.get("message", "?")
        lines.append(f"  [{severity}] {path}:{line} ({symbol}) — {msg}")
    return "\n".join(lines)


def _format_eslint_output(data: list) -> str:
    all_messages = []
    for file_result in data:
        path = file_result.get("filePath", "?")
        for msg in file_result.get("messages", []):
            severity = "ERROR" if msg.get("severity") == 2 else "WARN"
            line = msg.get("line", "?")
            rule = msg.get("ruleId", "?")
            message = msg.get("message", "?")
            all_messages.append((severity, f"  [{severity}] {path}:{line} ({rule}) — {message}"))

    if not all_messages:
        return "ESLint: No issues found. ✅"

    # Sort ERRORs first
    all_messages.sort(key=lambda x: 0 if x[0] == "ERROR" else 1)
    top = all_messages[:25]
    lines = [f"ESLint Static Analysis — {len(all_messages)} issues found (showing top {len(top)}):"]
    lines.extend([m[1] for m in top])
    return "\n".join(lines)
