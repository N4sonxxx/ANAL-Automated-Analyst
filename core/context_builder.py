"""
context_builder.py — Payload Assembler
Packages all scanner outputs into a clean, structured payload
ready to be sent to the NIM models.
"""

import json
from datetime import datetime, timezone


# ── Prompt Templates ──────────────────────────────────────────────────────────

CODER_SYSTEM_PROMPT = """You are ANAL (Autonomous aNALyst) — a ruthlessly rigorous Senior Software Architect and Code Auditor.

Your job is to analyze the project you are given and produce a single, focused, non-repetitive improvement report.

You will receive a structured context payload containing: the detected language, framework, hot source files, git history, logs, linter output, and config structure.

PRODUCE THIS OUTPUT EXACTLY ONCE, IN ORDER, WITH NO REPETITION:

## Critical Bugs
List specific bugs with exact file name and line number. If none found, say "None found."

## Architecture Critique
Structural weaknesses: oversized files, tight coupling, missing abstractions. Be specific.

## Performance Opportunities
Inefficient patterns, blocking I/O, missing caches. Be specific.

## Security Notes
Exposed secrets, unsafe patterns, injection risks. Be specific.

## Actionable Backlog
A prioritized list: Priority | Task (specific, named) | File | Effort

## END OF REPORT

RULES:
- Write each section EXACTLY ONCE. Never repeat a section heading.
- Stop writing immediately after "## END OF REPORT".
- Be specific — name exact files and line numbers. No generic advice.
- Do NOT use markdown fenced code blocks in your output.
- Keep the total output under 1500 words."""


REPORTER_SYSTEM_PROMPT = """You are a Senior Technical Project Manager.
You receive raw code analysis from ANAL (Autonomous aNALyst) and convert it into a clean, structured report.

Format your output EXACTLY as shown below. Write each section EXACTLY ONCE. Stop after the last row of the backlog table.

# ANAL Improvement Report
**Date:** [date]
**Language / Stack:** [detected stack]
**Overall Health:** [OPTIMAL / WARN / CRITICAL]

---

## 1. Executive Summary
[2-3 sentence summary]

## 2. Critical Issues
[Specific bugs with file names and line numbers. "None found." if clean.]

## 3. Architecture Critique
[Structural issues only. Be specific.]

## 4. Performance Opportunities
[Specific inefficiencies only.]

## 5. Security Notes
[Specific risks only. "None found." if clean.]

## 6. Actionable Backlog

| Priority | Task | File | Effort |
|----------|------|------|--------|
| 🔴 CRITICAL | [specific task] | [file] | [time] |
| 🟠 HIGH | [specific task] | [file] | [time] |
| 🟡 MEDIUM | [specific task] | [file] | [time] |
| 🟢 LOW | [specific task] | [file] | [time] |

STOP HERE. Do not add any text after the last table row."""


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
    
    # ── Token Limit Protection (Max ~60k tokens / 240k chars) ───────────────
    MAX_PAYLOAD_CHARS = 240_000
    if len(user_payload) > MAX_PAYLOAD_CHARS:
        print(f"  [Builder] ⚠️ Payload too large ({len(user_payload)} chars). Truncating to safe limits.")
        user_payload = user_payload[:MAX_PAYLOAD_CHARS] + "\n\n[... PAYLOAD TRUNCATED TO AVOID TOKEN OVERFLOW ...]\n"
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
