"""
ANAL.py - Autonomous aNALyst v1.0
===================================
Single entry point. Combines the Rich CLI and the 5-model NIM pipeline
into one application. No subprocesses.

Usage:
  python ANAL.py                   <- interactive CLI menu
  python ANAL.py --project-path "C:/path/to/project"
  python ANAL.py --project-path "C:/path/to/project" --dry-run
  python ANAL.py --project-path "C:/path/to/project" --skip-linter --skip-safety
"""

import os
import re
import sys
import glob
import argparse
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich import box
from rich.rule import Rule
from rich.markdown import Markdown
import signal

from scanner import project_detector, file_harvester, linter_runner
from core import context_builder, nim_client, reporter

# ─── Branding ─────────────────────────────────────────────────────────────────
console = Console()

ASCII_LOGO = """
[bold purple] █████╗ ███╗   ██╗ █████╗ ██╗
██╔══██╗████╗  ██║██╔══██╗██║
███████║██╔██╗ ██║███████║██║
██╔══██║██║╚██╗██║██╔══██║██║
██║  ██║██║ ╚████║██║  ██║███████╗
╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝╚══════╝[/bold purple]"""

SUBTITLE  = "// AUTONOMOUS aNALyst — NVIDIA NIM EDITION"
SEP       = "-" * 60
BANNER    = """
+----------------------------------------------------------+
|        ANAL - Autonomous aNALyst v1.0                   |
|        Powered by NVIDIA NIM -- 5-Model Pipeline        |
+----------------------------------------------------------+
"""


# ─── Pipeline Core ────────────────────────────────────────────────────────────

def run_pipeline(
    project_path: str,
    skip_linter:  bool = False,
    skip_safety:  bool = False,
    dry_run:      bool = False,
    model_override: str = None,
) -> str | None:
    """
    Execute the full 5-model NIM analysis pipeline on a project directory.
    Returns the path to the saved report, or None on failure / dry-run.
    """
    project_path = os.path.abspath(project_path)

    if not os.path.isdir(project_path):
        console.print(f"\n[red]  ERROR: Path does not exist or is not a directory:[/red] {project_path}")
        return None

    console.print(f"\n  Target Project: [purple]{project_path}[/purple]\n")

    # ── STEP 1: Project Detection ──────────────────────────────────────────────
    console.print(SEP)
    console.print("  STEP 1/6 -- Project Detection")
    console.print(SEP)
    profile = project_detector.detect(project_path)

    # ── STEP 2: Content Harvesting ─────────────────────────────────────────────
    console.print("\n" + SEP)
    console.print("  STEP 2/6 -- Content Harvesting")
    console.print(SEP)
    harvested = file_harvester.harvest(project_path, profile)

    # ── STEP 3: Static Analysis ────────────────────────────────────────────────
    console.print("\n" + SEP)
    console.print("  STEP 3/6 -- Static Analysis")
    console.print(SEP)
    if skip_linter:
        lint_output = "Static analysis skipped (--skip-linter)."
        console.print("  [Linter] Skipped.")
    else:
        lint_output = linter_runner.run(project_path, profile)

    # ── STEP 3B: Vector Indexing (NV-EmbedCode) ────────────────────────────────
    console.print("\n" + SEP)
    console.print("  STEP 3B/6 -- Vector Indexing & Retrieval")
    console.print(SEP)

    file_chunks    = []
    chunk_to_file  = {}
    for f in harvested["hot_files"][:100]:
        chunk_text = f"File: {f['path']}\n\n{f['content'][:2000]}"
        file_chunks.append(chunk_text)
        chunk_to_file[chunk_text] = f

    if file_chunks and os.getenv("NIM_API_KEY"):
        try:
            embeddings  = nim_client.embed_texts(file_chunks)
            query       = "critical business logic, configuration, security vulnerabilities, and core application architecture"
            top_chunks  = nim_client.retrieve_relevant_chunks(query, file_chunks, embeddings, top_k=10)
            harvested["hot_files"] = [chunk_to_file[c] for c in top_chunks]
            console.print(f"  [Embedder] Successfully retrieved [green]{len(harvested['hot_files'])}[/green] most relevant files.")
        except Exception as e:
            console.print(f"  [Embedder] [yellow]Vector indexing failed: {e}. Using top 10 recent files.[/yellow]")
            harvested["hot_files"] = harvested["hot_files"][:10]
    else:
        harvested["hot_files"] = harvested["hot_files"][:10]
        console.print("  [Embedder] [dim]API key not set in dry-run. Using top 10 recent files.[/dim]")

    # ── STEP 4: Assemble Payload ───────────────────────────────────────────────
    console.print("\n" + SEP)
    console.print("  STEP 4/6 -- Assembling NIM Payload")
    console.print(SEP)
    payload = context_builder.assemble(profile, harvested, lint_output)

    # ── DRY RUN: stop here ─────────────────────────────────────────────────────
    if dry_run:
        console.print("\n" + "=" * 60)
        console.print("  DRY RUN -- Payload Preview (no API calls made)")
        console.print("=" * 60)
        preview = payload["user_payload"][:3000]
        console.print(preview)
        remaining = len(payload["user_payload"]) - 3000
        if remaining > 0:
            console.print(f"\n  ... [{remaining} more chars in full payload]")
        console.print(f"\n  Estimated tokens: [purple]~{payload['estimated_tokens']:,}[/purple]")
        console.print("  [dim]Re-run without --dry-run to execute the full pipeline.[/dim]")
        return None

    if not os.getenv("NIM_API_KEY"):
        console.print("[red]  ERROR: NIM_API_KEY not set. Add it to your .env file.[/red]")
        return None

    if model_override:
        os.environ["MODEL_CODER"] = model_override

    # ── STEP 5A: Qwen3 Coder 480B (Streaming) ─────────────────────────────────
    console.print("\n" + SEP)
    console.print("  STEP 5A/6 -- Qwen3 Coder 480B -- Deep Analysis (Streaming)")
    console.print(SEP)
    raw_analysis = nim_client.analyze_code(
        system_prompt=payload["coder_system_prompt"],
        user_payload=payload["user_payload"],
        stream=True,
    )

    # ── STEP 5B: Reranker -- Issue Prioritization ──────────────────────────────
    console.print("\n" + SEP)
    console.print("  STEP 5B/6 -- Reranker -- Issue Prioritization")
    console.print(SEP)
    sections   = re.split(r"\n(?=#{2,3}\s)", raw_analysis)
    paragraphs = [s.strip() for s in sections if len(s.strip()) > 50]
    if len(paragraphs) > 1:
        raw_analysis_ranked = "\n\n".join(
            nim_client.rerank_issues(
                query="critical bugs, security vulnerabilities, and high-priority performance issues",
                passages=paragraphs,
            )
        )
    else:
        raw_analysis_ranked = raw_analysis
        console.print("  [Reranker] [dim]Not enough sections to rerank. Using original order.[/dim]")

    # ── STEP 5C: Nemotron Super 49B -- Report Structuring (Streaming) ──────────
    console.print("\n" + SEP)
    console.print("  STEP 5C/6 -- Nemotron Super 49B -- Report Structuring (Streaming)")
    console.print(SEP)
    structured_report = nim_client.generate_report(
        system_prompt=payload["reporter_system_prompt"],
        raw_analysis=raw_analysis_ranked,
    )

    # ── STEP 5D: Content Safety 4B ─────────────────────────────────────────────
    console.print("\n" + SEP)
    console.print("  STEP 5D/6 -- Content Safety 4B -- Hallucination Validation")
    console.print(SEP)
    if skip_safety:
        is_safe, safety_note = True, "Safety check skipped (--skip-safety)."
        console.print("  [Safety] Skipped.")
    else:
        is_safe, safety_note = nim_client.validate_safety(structured_report)
        status = "[green]SAFE[/green]" if is_safe else "[red]FLAGGED[/red]"
        console.print(f"  [Safety] Result: {status} — {safety_note}")

    # ── STEP 6: Save Report ────────────────────────────────────────────────────
    console.print("\n" + SEP)
    console.print("  STEP 6/6 -- Saving Report")
    console.print(SEP)
    report_path = reporter.save(
        report_text=structured_report,
        project_path=project_path,
        metadata=payload["metadata"],
        is_safe=is_safe,
        safety_note=safety_note,
    )
    reporter.print_summary(structured_report)
    console.print(f"\n  [green]Done![/green] Full report saved to:\n  [purple]{report_path}[/purple]\n")
    return report_path


# ─── CLI Menu ─────────────────────────────────────────────────────────────────

def clear():
    os.system("cls" if os.name == "nt" else "clear")


def header():
    console.print(ASCII_LOGO)
    console.print(f"[dim]{SUBTITLE}[/dim]\n")


def main_menu():
    clear()
    header()
    console.print(Rule("[dim]main menu[/dim]", style="purple"))

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    table.add_column(style="bold purple", width=4)
    table.add_column(style="white")
    table.add_column(style="dim", justify="right")
    table.add_row("01", "Analyze Project", "scan + generate report")
    table.add_row("02", "History",         "view past reports")
    table.add_row("03", "Model Config",    "view active nim models")
    table.add_row("04", "Exit",            "")
    console.print(table)
    console.print()

    choice = Prompt.ask(
        "[purple]>[/purple]",
        choices=["01", "02", "03", "04", "1", "2", "3", "4"],
        show_choices=False,
    )
    return {"01":"1","1":"1","02":"2","2":"2","03":"3","3":"3","04":"4","4":"4"}[choice]


def analyze_menu():
    clear()
    header()
    console.print(Rule("[dim]analyze project[/dim]", style="purple"))
    console.print("[dim]main[/dim] / [purple]analyze project[/purple]\n")

    project_path = Prompt.ask("[dim]project path[/dim] [purple]>[/purple]")
    project_path = os.path.abspath(project_path)

    if not os.path.isdir(project_path):
        console.print(f"\n[red]  Path not found:[/red] {project_path}")
        Prompt.ask("\n[dim]press enter to go back[/dim]")
        return

    console.print()
    console.print(Rule("[dim]options[/dim]", style="dim"))
    skip_linter    = not Confirm.ask("[white]enable linter?[/white]",         default=True)
    skip_safety    = not Confirm.ask("[white]enable safety check?[/white]",    default=True)
    dry_run        =     Confirm.ask("[white]dry run (no api calls)?[/white]",  default=False)
    model_override = None
    console.print()
    if Confirm.ask("[white]override primary model?[/white]", default=False):
        model_override = Prompt.ask("[dim]model id[/dim] [purple]>[/purple]")

    console.print()
    console.print(Panel(
        f"[dim]path:[/dim]    [purple]{project_path}[/purple]\n"
        f"[dim]linter:[/dim]  {'[green]on[/green]' if not skip_linter else '[red]off[/red]'}\n"
        f"[dim]safety:[/dim]  {'[green]on[/green]' if not skip_safety else '[red]off[/red]'}\n"
        f"[dim]dry run:[/dim] {'[yellow]yes[/yellow]' if dry_run else '[green]no[/green]'}",
        title="[purple]anal configuration[/purple]",
        border_style="purple",
        box=box.ROUNDED,
    ))
    console.print()

    if not Confirm.ask("[purple]> start analysis?[/purple]", default=True):
        return

    clear()
    header()
    console.print(Rule("[dim]running pipeline[/dim]", style="purple"))
    console.print("[dim]main[/dim] / analyze / [purple]running[/purple]\n")

    try:
        run_pipeline(project_path, skip_linter, skip_safety, dry_run, model_override)
    except KeyboardInterrupt:
        console.print("\n\n[yellow]  Analysis interrupted by user (Ctrl+C).[/yellow]")

    console.print()
    console.print(Rule(style="purple"))
    Prompt.ask("\n[dim]press enter to return to main menu[/dim]")


def history_menu():
    while True:
        clear()
        header()
        console.print(Rule("[dim]anal history[/dim]", style="purple"))
        console.print("[dim]main[/dim] / [purple]history[/purple]\n")

        reports = sorted(glob.glob("./anal_*.md"), reverse=True)

        if not reports:
            console.print("[dim]No reports found yet. Run an analysis first.[/dim]")
            console.print()
            Prompt.ask("[dim]press enter to go back[/dim]")
            return

        table = Table(box=box.SIMPLE, show_header=True, header_style="dim")
        table.add_column("id",     style="bold purple", width=4)
        table.add_column("date",   style="dim",    width=20)
        table.add_column("file",   style="purple")
        table.add_column("size",   style="dim", justify="right")
        
        for idx, r in enumerate(reports[:10]):
            stat  = os.stat(r)
            mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            size  = f"{max(1, stat.st_size // 1024)} KB"
            table.add_row(f"{idx+1:02d}", mtime, os.path.basename(r), size)
        
        console.print(table)
        console.print("\n[dim]enter the ID of the report to view it, or leave blank to go back.[/dim]")
        
        choice = Prompt.ask("[purple]>[/purple]")
        
        if not choice.strip():
            return
            
        try:
            choice_idx = int(choice) - 1
            if 0 <= choice_idx < len(reports[:10]):
                clear()
                header()
                selected_report = reports[choice_idx]
                console.print(Rule(f"[dim]viewing: {os.path.basename(selected_report)}[/dim]", style="purple"))
                
                with open(selected_report, "r", encoding="utf-8") as f:
                    content = f.read()
                
                console.print(Markdown(content))
                console.print(Rule(style="purple"))
                Prompt.ask("\n[dim]press enter to return to history menu[/dim]")
            else:
                console.print("[red]Invalid selection.[/red]")
                import time; time.sleep(1)
        except ValueError:
            pass


def model_config_menu():
    clear()
    header()
    console.print(Rule("[dim]model config[/dim]", style="purple"))
    console.print("[dim]main[/dim] / [purple]model config[/purple]\n")

    table = Table(box=box.SIMPLE, show_header=True, header_style="dim")
    table.add_column("step",     style="bold purple", width=6)
    table.add_column("role",     style="white",       width=24)
    table.add_column("model id", style="purple dim")
    for step, role, key, default in [
        ("3B",  "embeddings",       "MODEL_EMBEDDER",  "nvidia/nv-embedcode-7b-v1"),
        ("5A",  "coder agent",      "MODEL_CODER",     "qwen/qwen3-coder-480b-a35b-instruct"),
        ("5B",  "reranker",         "MODEL_RERANKER",  "meta/llama-3.1-8b-instruct"),
        ("5C",  "report writer",    "MODEL_REPORTER",  "nvidia/llama-3.3-nemotron-super-49b-v1.5"),
        ("5D",  "safety validator", "MODEL_SAFETY",    "nvidia/nemotron-content-safety-reasoning-4b"),
    ]:
        table.add_row(step, role, os.getenv(key, default))

    console.print(table)
    console.print("\n[dim]To change models, edit your [purple].env[/purple] file:[/dim]")
    console.print("[dim]MODEL_CODER, MODEL_EMBEDDER, MODEL_RERANKER, MODEL_REPORTER, MODEL_SAFETY[/dim]")
    console.print()
    Prompt.ask("[dim]press enter to go back[/dim]")


# ─── Entry Point ──────────────────────────────────────────────────────────────

def cli_mode():
    """Launch the interactive Rich terminal menu."""
    try:
        while True:
            choice = main_menu()
            if   choice == "1": analyze_menu()
            elif choice == "2": history_menu()
            elif choice == "3": model_config_menu()
            elif choice == "4":
                clear()
                console.print("\n[purple]goodbye.[/purple]\n")
                if os.name == 'nt':
                    try:
                        os.kill(os.getppid(), signal.SIGTERM)
                    except Exception:
                        os.system(f"taskkill /PID {os.getppid()} /F /T >nul 2>&1")
                sys.exit(0)
    except KeyboardInterrupt:
        clear()
        console.print("\n[purple]goodbye.[/purple]\n")
        sys.exit(0)


def headless_mode():
    """Run the pipeline directly from CLI args (for scripted / CI use)."""
    print(BANNER)
    parser = argparse.ArgumentParser(
        prog="ANAL.py",
        description="Autonomous aNALyst — AI-powered codebase auditor",
    )
    parser.add_argument("--project-path", required=True, help="Absolute path to the project to audit.")
    parser.add_argument("--dry-run",       action="store_true", help="Preview payload without calling the API.")
    parser.add_argument("--skip-linter",   action="store_true", help="Skip static analysis.")
    parser.add_argument("--skip-safety",   action="store_true", help="Skip safety validation.")
    parser.add_argument("--model",         default=None,        help="Override the primary coder model ID.")
    args = parser.parse_args()

    run_pipeline(
        project_path=args.project_path,
        skip_linter=args.skip_linter,
        skip_safety=args.skip_safety,
        dry_run=args.dry_run,
        model_override=args.model,
    )


if __name__ == "__main__":
    # If --project-path is passed, run headless (scripted mode)
    # Otherwise, launch the interactive CLI
    if "--project-path" in sys.argv:
        headless_mode()
    else:
        cli_mode()
