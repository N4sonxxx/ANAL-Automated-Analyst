# Universal Project Improver (UPI)
## Zero-Config AI-Powered Codebase Auditor

The **Universal Project Improver (UPI)** is a fully autonomous AI audit engine that can be pointed at **any software project on your machine** and immediately begin analyzing, diagnosing, and improving it — with zero manual configuration required.

---

## 1. System Vision & Objective

UPI is a **"plug-and-play" code doctor**. You give it a folder path. It figures out the rest.

It does not need you to tell it what language the project uses, where the logs are, or what the project is for. It discovers all of this automatically by scanning the project like a detective. It then sends everything to a powerful LLM (NVIDIA NIM) and produces a professional daily improvement report covering:

- **Code Quality Issues:** Bugs, anti-patterns, dead code, and security vulnerabilities.
- **Architectural Weaknesses:** Tight coupling, missing abstractions, scaling bottlenecks.
- **Recent Problem Areas:** Files that have been changed the most (hot files = likely buggy files).
- **Actionable Fixes:** Specific lines of code, prompt edits, or config changes to improve the project today.

---

## 2. The Core Philosophy: Zero Configuration

The original CASA design required a custom `trading_adapter.py` — a module that knew exactly where `trade_outcomes.csv` lived. **UPI throws this away.**

Instead, UPI uses a single **Universal Scanner** that works on every project by applying generic discovery rules:

| Discovery Rule | What It Finds |
|---|---|
| Look for `package.json`, `requirements.txt`, `go.mod`, `Cargo.toml`, `pom.xml` | Identifies the language and tech stack |
| Look for `README.md`, `docs/`, `CHANGELOG.md` | Reads the project's purpose and history |
| Run `git log --oneline -30` | Finds what has been worked on recently |
| Find all `*.log`, `*.err`, `crash_report*` files | Surfaces runtime errors automatically |
| Get the 10 most recently modified source files | Finds the "active zone" where bugs live |
| Run language-specific linters (e.g., `pylint`, `eslint`) | Gets static analysis results |

No adapter needed. No config file needed. Just a folder path.

---

## 3. Directory Layout

```
universal_project_improver/
├── scanner/
│   ├── __init__.py
│   ├── project_detector.py     # Identifies language, framework, and project type
│   ├── file_harvester.py       # Collects relevant files, logs, and git history
│   └── linter_runner.py        # Runs language-appropriate linters
├── core/
│   ├── __init__.py
│   ├── context_builder.py      # Packages all scanner output into a clean LLM payload
│   ├── nim_client.py           # NVIDIA NIM API client with retry and token truncation
│   └── reporter.py             # Writes the final Markdown improvement report
├── main.py                     # CLI entry point
├── requirements.txt
└── .env                        # NVIDIA NIM API key
```

---

## 4. How to Run (The Whole Point)

Point it at any project and it just works:

```bash
# Audit a Python trading bot
python main.py --project-path "C:/Users/N4sonxxx/Documents/Project A"

# Audit a Node.js web app
python main.py --project-path "C:/Users/N4sonxxx/Documents/MyWebApp"

# Audit a Go microservice
python main.py --project-path "C:/Users/N4sonxxx/Documents/GoService"

# See what it would say without saving anything
python main.py --project-path "C:/Users/N4sonxxx/Documents/Project A" --dry-run
```

The report is always saved as `UPI_Report_YYYY-MM-DD.md` inside the target project's root folder.

---

## 5. Context Package Files

- **README.md** *(This File)*: Vision, philosophy, and usage.
- **ARCHITECTURE.md**: Data pipeline, component map, and Mermaid diagram.
- **SCHEMAS.md**: JSON payload structure and Markdown report template.
- **PROMPTS.md**: System prompt and ingestion template for NVIDIA NIM.
- **IMPLEMENTATION_STEPS.md**: Step-by-step build guide.
