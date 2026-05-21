"""
file_harvester.py — Content Collector
Gathers: hot files, git history, log tails, and config structures.
Applies token budget management to avoid exceeding model context limits.
"""

import os
import subprocess
from collections import deque
from scanner.project_detector import SKIP_DIRS

# ── Token Budget Config ──────────────────────────────────────────────────────
# Rough limit: 200K chars ≈ 50K tokens (safe for 256K context Qwen3 model)
MAX_CHARS = 200_000
MAX_HOT_FILES = 10
MAX_LOG_LINES = 200
MAX_GIT_COMMITS = 30


def harvest(project_path: str, profile: dict) -> dict:
    """
    Collect all relevant project content.

    Returns:
        {
            "hot_files": list[dict],      # [{path, content}]
            "git_history": str,
            "log_tail": str,
            "config_structure": dict,
            "total_chars": int,
        }
    """
    print(f"  [Harvester] Collecting content from {project_path}...")

    hot_files     = _get_hot_files(project_path, profile["extensions"])
    git_history   = _get_git_history(project_path)
    log_tail      = _get_logs(project_path)
    config_struct = _get_configs(project_path)

    # ── Token Budget Management ──────────────────────────────────────────────
    total_chars = (
        sum(len(f["content"]) for f in hot_files)
        + len(git_history)
        + len(log_tail)
        + len(str(config_struct))
    )

    print(f"  [Harvester] Raw context size: {total_chars:,} chars (~{total_chars // 4:,} tokens)")

    # Trim lower-priority content if over budget
    if total_chars > MAX_CHARS:
        print(f"  [Harvester] Over budget — trimming lower-priority content...")
        # Trim git history first
        git_history = git_history[:2000] + "\n[... trimmed ...]"
        # Trim log tail
        log_tail = log_tail[:3000] + "\n[... trimmed ...]"
        # Trim each hot file to first 3000 chars if still over budget
        total_chars = sum(len(f["content"]) for f in hot_files) + len(git_history) + len(log_tail)
        if total_chars > MAX_CHARS:
            for f in hot_files:
                if len(f["content"]) > 3000:
                    f["content"] = f["content"][:3000] + "\n[... file trimmed ...]"

    result = {
        "hot_files":        hot_files,
        "git_history":      git_history,
        "log_tail":         log_tail,
        "config_structure": config_struct,
        "total_chars":      total_chars,
    }

    print(f"  [Harvester] Done. {len(hot_files)} hot files, git: {bool(git_history)}, logs: {bool(log_tail)}")
    return result


# ── Sub-Collectors ────────────────────────────────────────────────────────────

def _get_hot_files(project_path: str, extensions: list[str]) -> list[dict]:
    """
    Find the N most recently modified source files in the project.
    Skips common noise directories (node_modules, __pycache__, etc.)
    """
    all_files = []

    for dirpath, dirnames, filenames in os.walk(project_path):
        # Prune skip directories in-place so os.walk doesn't descend into them
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

        for filename in filenames:
            if any(filename.endswith(ext) for ext in extensions):
                full_path = os.path.join(dirpath, filename)
                try:
                    mtime = os.path.getmtime(full_path)
                    all_files.append((mtime, full_path))
                except OSError:
                    pass

    # Don't sort, just grab all of them (up to 500 files to prevent memory issues)
    top_files = all_files[:500]

    result = []
    for mtime, full_path in top_files:
        rel_path = os.path.relpath(full_path, project_path)
        try:
            content = open(full_path, encoding="utf-8", errors="ignore").read()
            result.append({"path": rel_path, "content": content})
        except Exception as e:
            result.append({"path": rel_path, "content": f"[Could not read: {e}]"})

    return result


def _get_git_history(project_path: str) -> str:
    """
    Run git log to retrieve the last N commit messages.
    Returns an empty string if git is not available or not a repo.
    """
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", f"-{MAX_GIT_COMMITS}"],
            capture_output=True,
            text=True,
            cwd=project_path,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return ""
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        return ""


def _get_logs(project_path: str) -> str:
    """
    Walk the project and find log/error files.
    Read the last N lines of each and aggregate them.
    """
    log_extensions = {".log", ".err", ".out"}
    log_name_hints = {"error", "crash", "debug", "app", "server", "output"}

    log_chunks = []

    for dirpath, dirnames, filenames in os.walk(project_path):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

        for filename in filenames:
            name_lower = filename.lower()
            is_log = (
                any(filename.endswith(ext) for ext in log_extensions)
                or any(hint in name_lower for hint in log_name_hints)
            )
            if is_log:
                full_path = os.path.join(dirpath, filename)
                rel_path = os.path.relpath(full_path, project_path)
                tail = _tail_file(full_path, MAX_LOG_LINES)
                if tail:
                    log_chunks.append(f"--- LOG: {rel_path} ---\n{tail}")

    return "\n\n".join(log_chunks) if log_chunks else "No log files found."


def _tail_file(filepath: str, n: int) -> str:
    """Read the last N lines of a file efficiently."""
    try:
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            last_lines = deque(f, maxlen=n)
        return "".join(last_lines)
    except Exception:
        return ""


def _get_configs(project_path: str) -> dict:
    """
    Locate common config files and return their content or key structure.
    Never reads values from .env files — only key names.
    """
    config_info = {}

    # Files to read fully (non-sensitive)
    readable_configs = [
        "config.json", "settings.json", "appsettings.json",
        "docker-compose.yml", "docker-compose.yaml",
        "pyproject.toml", "setup.cfg",
    ]

    for cfg_name in readable_configs:
        cfg_path = os.path.join(project_path, cfg_name)
        if os.path.isfile(cfg_path):
            try:
                content = open(cfg_path, encoding="utf-8", errors="ignore").read()
                config_info[cfg_name] = content[:2000]  # Cap at 2000 chars
            except Exception:
                pass

    # .env — read KEYS ONLY, never values
    env_path = os.path.join(project_path, ".env")
    if os.path.isfile(env_path):
        try:
            keys = []
            for line in open(env_path, encoding="utf-8", errors="ignore"):
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key = line.split("=", 1)[0].strip()
                    keys.append(key)
            config_info[".env (keys only)"] = keys
        except Exception:
            pass

    return config_info
