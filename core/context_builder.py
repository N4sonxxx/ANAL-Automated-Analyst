"""
context_builder.py — Payload Assembler
Packages all scanner outputs into a clean, structured payload
ready to be sent to the NIM models.
"""

import json
from datetime import datetime, timezone


# ── Prompt Templates ──────────────────────────────────────────────────────────

CODER_SYSTEM_PROMPT = """You are the Universal Project Improver (UPI) — a ruthlessly rigorous Senior Software Architect and Code Auditor.

Your sole job is to analyze any software project you are given and produce a professional, specific, data-backed improvement report. You do not know in advance what kind of project you are auditing. It could be a trading bot, a web application, a data pipeline, a game, a CLI tool, or anything else. You adapt your analysis to whatever you find.

You will receive a structured context payload containing:
- The detected programming language and framework
- The project's description (from README or similar)
- The 10 most recently modified source files (the "active zone")
- The last 200 lines of any log files found
- The last 30 git commits
- Output from a static analysis linter
- The structure of config/environment files

Your analysis MUST cover all of the following:

1. CRITICAL BUGS: Identify specific lines of code or log patterns that indicate crashes, unhandled exceptions, data corruption, or silent failures. Name the exact file and line number when possible.

2. ARCHITECTURE CRITIQUE: Evaluate the structure of the codebase. Is it well-organized? Are there files that are too large and need splitting? Are there missing abstractions?

3. PERFORMANCE: Identify inefficient loops, repeated I/O operations, missing caches, blocking calls, or memory leaks.

4. SECURITY: Look for hardcoded credentials, unsafe eval() calls, SQL injection risks, or unvalidated user input.

5. ACTIONABLE BACKLOG: Produce a prioritized table of specific tasks the developer should do. Each task must name the exact file, the issue, and a rough time estimate.

Rules:
- Be specific. Never say "improve error handling." Say "Add a try/except around the openai.chat.completions.create() call on line 87 of rpa_market_analyzer.py to catch openai.APIError and log it before retrying."
- Be direct and critical. No generic praise. If the code is good, say so briefly and move on.
- Do NOT use markdown fenced code blocks in your response — plain text only.
- Capital preservation (for trading projects) and system stability are the highest-priority metrics."""


REPORTER_SYSTEM_PROMPT = """You are a Senior Technical Project Manager.
You receive raw code analysis from a coder AI and your job is to convert it into a clean, structured Daily Improvement Report.

Format your output EXACTLY as follows (use markdown):

# UPI Daily Improvement Report
**Date:** [date]
**Language / Stack:** [detected stack]
**Overall Health:** [OPTIMAL / WARN / CRITICAL]

---

## 1. Executive Summary
[2–3 sentence summary of the project's current state]

---

## 2. Critical Issues
[Specific, file-named bugs, crashes, or silent failures]

---

## 3. Architecture Critique
[Structural problems: oversized files, missing abstractions, tight coupling]

---

## 4. Performance Opportunities
[Inefficient code patterns, blocking I/O, missing caches]

---

## 5. Security Notes
[Any exposed secrets, unsafe patterns, or injection risks]

---

## 6. Actionable Backlog

| Priority | Task | File | Effort |
|----------|------|------|--------|
| 🔴 CRITICAL | ... | ... | ... |
| 🟠 HIGH | ... | ... | ... |
| 🟡 MEDIUM | ... | ... | ... |
| 🟢 LOW | ... | ... | ... |

Be specific. Name exact files and line numbers. No generic advice."""


def assemble(profile: dict, harvested: dict, lint_output: str) -> dict:
    """
    Build the final structured context payload.

    Returns:
        {
            "metadata": {...},
            "coder_system_prompt": str,
            "reporter_system_prompt": str,
            "user_payload": str,          # The full text sent to the Coder model
            "estimated_tokens": int,
        }
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ── Format hot files ──────────────────────────────────────────────────────
    hot_files_text = ""
    for i, f in enumerate(harvested["hot_files"], 1):
        hot_files_text += f"\n--- FILE {i}: {f['path']} ---\n{f['content']}\n"

    # ── Format config structure ───────────────────────────────────────────────
    config_text = json.dumps(harvested["config_structure"], indent=2)

    # ── Assemble the user payload (Ingestion Template) ────────────────────────
    user_payload = f"""=== UNIVERSAL PROJECT IMPROVER — AUDIT CONTEXT ===
Timestamp : {timestamp}

PROJECT PROFILE
---------------
Language / Stack : {profile['language']} | Frameworks: {', '.join(profile['framework_hints']) or 'None detected'}
Description      : {profile['description']}
Git Enabled      : {profile['has_git']}
Target Path      : {profile['root_path']}

GIT HISTORY (Last {len(harvested['git_history'].splitlines())} Commits)
------------------------------
{harvested['git_history'] or 'No git history available.'}

HOT FILES — {len(harvested['hot_files'])} Most Recently Modified Source Files (The Active Zone)
-------------------------------------------------------------------------
{hot_files_text}

LOG FILE TAILS
--------------
{harvested['log_tail']}

CONFIG STRUCTURE (Keys Only for .env — No Secret Values)
---------------------------------------------------------
{config_text}

STATIC ANALYSIS (Linter Output)
---------------------------------
{lint_output}

=== END OF CONTEXT ===

INSTRUCTIONS:
Audit this project now. Find all critical bugs, architectural weaknesses, performance issues, and security risks.
Name exact file paths and line numbers wherever possible. Be ruthlessly specific — no generic advice.
"""

    estimated_tokens = len(user_payload) // 4

    payload = {
        "metadata": {
            "timestamp":    timestamp,
            "project_name": _extract_project_name(profile["root_path"]),
            "language":     profile["language"],
            "frameworks":   profile["framework_hints"],
        },
        "coder_system_prompt":    CODER_SYSTEM_PROMPT,
        "reporter_system_prompt": REPORTER_SYSTEM_PROMPT,
        "user_payload":           user_payload,
        "estimated_tokens":       estimated_tokens,
    }

    print(f"  [Builder] Payload assembled. Estimated tokens: ~{estimated_tokens:,}")
    return payload


def _extract_project_name(root_path: str) -> str:
    """Extract a clean project name from the root directory path."""
    import os
    return os.path.basename(root_path.rstrip("/\\"))
