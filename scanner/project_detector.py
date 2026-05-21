"""
project_detector.py — Project Fingerprinter
Sniffs any folder and determines: language, framework, and purpose.
Requires zero configuration from the user.
"""

import os
import subprocess


# Maps signature filenames → detected language
LANGUAGE_SIGNATURES = {
    "requirements.txt":  "Python",
    "pyproject.toml":    "Python",
    "setup.py":          "Python",
    "package.json":      "JavaScript/TypeScript",
    "go.mod":            "Go",
    "Cargo.toml":        "Rust",
    "pom.xml":           "Java",
    "build.gradle":      "Java",
    "composer.json":     "PHP",
    "Gemfile":           "Ruby",
    "*.sln":             "C#",
    "*.csproj":          "C#",
}

# Maps language → typical source file extensions
LANGUAGE_EXTENSIONS = {
    "Python":               [".py"],
    "JavaScript/TypeScript":[".js", ".ts", ".jsx", ".tsx"],
    "Go":                   [".go"],
    "Rust":                 [".rs"],
    "Java":                 [".java"],
    "PHP":                  [".php"],
    "Ruby":                 [".rb"],
    "C#":                   [".cs"],
    "Unknown":              [".py", ".js", ".ts", ".go", ".rs", ".java", ".cs", ".php", ".rb"],
}

# Directories to always skip during scanning
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", "venv", ".venv",
    "env", "dist", "build", "target", ".idea", ".vscode",
    "bin", "obj", ".gradle", "vendor",
}


def detect(project_path: str) -> dict:
    """
    Fingerprint a project directory and return a ProjectProfile dict.

    Returns:
        {
            "language": str,
            "extensions": list[str],
            "framework_hints": list[str],
            "description": str,
            "has_git": bool,
            "root_path": str,
        }
    """
    print(f"  [Detector] Scanning project at: {project_path}")

    language = "Unknown"
    framework_hints = []

    # ── Language Detection ──────────────────────────────────────────────────
    root_files = set()
    try:
        root_files = set(os.listdir(project_path))
    except PermissionError:
        pass

    for sig, lang in LANGUAGE_SIGNATURES.items():
        # Handle wildcard patterns like *.sln
        if sig.startswith("*"):
            ext = sig[1:]
            if any(f.endswith(ext) for f in root_files):
                language = lang
                break
        elif sig in root_files:
            language = lang
            break

    print(f"  [Detector] Language detected: {language}")

    # ── Framework Hints ─────────────────────────────────────────────────────
    framework_hints = _detect_frameworks(project_path, language, root_files)

    # ── Project Description ─────────────────────────────────────────────────
    description = _read_description(project_path)

    # ── Git Check ───────────────────────────────────────────────────────────
    has_git = os.path.isdir(os.path.join(project_path, ".git"))

    profile = {
        "language":        language,
        "extensions":      LANGUAGE_EXTENSIONS.get(language, LANGUAGE_EXTENSIONS["Unknown"]),
        "framework_hints": framework_hints,
        "description":     description,
        "has_git":         has_git,
        "root_path":       project_path,
    }

    print(f"  [Detector] Frameworks: {framework_hints or ['None detected']}")
    print(f"  [Detector] Git repo: {has_git}")
    return profile


def _detect_frameworks(project_path: str, language: str, root_files: set) -> list:
    """Heuristically detect frameworks by scanning common config/package files."""
    hints = []

    if language == "Python":
        # Check requirements.txt for known packages
        req_path = os.path.join(project_path, "requirements.txt")
        if os.path.isfile(req_path):
            try:
                content = open(req_path, encoding="utf-8", errors="ignore").read().lower()
                for lib in ["fastapi", "flask", "django", "openai", "tensorflow",
                            "torch", "pandas", "metatrader5", "streamlit", "celery"]:
                    if lib in content:
                        hints.append(lib.capitalize())
            except Exception:
                pass

    elif language == "JavaScript/TypeScript":
        pkg_path = os.path.join(project_path, "package.json")
        if os.path.isfile(pkg_path):
            try:
                import json
                pkg = json.load(open(pkg_path, encoding="utf-8", errors="ignore"))
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                for lib in ["react", "next", "vue", "express", "nest", "vite", "webpack"]:
                    if lib in deps:
                        hints.append(lib.capitalize())
            except Exception:
                pass

    return hints[:6]  # Cap at 6 to avoid noise


def _read_description(project_path: str) -> str:
    """
    Try to extract a short project description from README.md.
    Falls back to a generic message if not found.
    """
    for readme_name in ["README.md", "readme.md", "README.txt", "readme.txt"]:
        readme_path = os.path.join(project_path, readme_name)
        if os.path.isfile(readme_path):
            try:
                content = open(readme_path, encoding="utf-8", errors="ignore").read()
                # Return the first 600 characters as the summary
                return content[:600].strip()
            except Exception:
                pass
    return "No README found. Project description unavailable."
