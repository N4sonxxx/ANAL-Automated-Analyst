# cli.py  —  drop this in your project root, run instead of main.py
import os
import sys
import subprocess
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text
from rich import box
from rich.columns import Columns
from rich.rule import Rule

console = Console()

ASCII_LOGO = """
[bold purple]██╗   ██╗██████╗ ██╗
██║   ██║██╔══██╗██║
██║   ██║██████╔╝██║
██║   ██║██╔═══╝ ██║
╚██████╔╝██║     ██║
 ╚═════╝ ╚═╝     ╚═╝[/bold purple]"""

HISTORY_FILE = ".upi_history.json"


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def header():
    console.print(ASCII_LOGO)
    console.print(
        "[dim]// UNIVERSAL PROJECT IMPROVER — NVIDIA NIM EDITION[/dim]\n"
    )


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
        "[purple]▶[/purple]",
        choices=["01", "02", "03", "04", "1", "2", "3", "4"],
        show_choices=False,
    )

    mapping = {"01":"1","1":"1","02":"2","2":"2","03":"3","3":"3","04":"4","4":"4"}
    return mapping[choice]


def analyze_menu():
    clear()
    header()
    console.print(Rule("[dim]analyze project[/dim]", style="purple"))
    console.print("[dim]main[/dim] / [purple]analyze project[/purple]\n")

    project_path = Prompt.ask("[dim]project path[/dim] [purple]▶[/purple]")
    project_path = os.path.abspath(project_path)

    if not os.path.isdir(project_path):
        console.print(f"\n[red]✗ path not found:[/red] {project_path}")
        Prompt.ask("\n[dim]press enter to go back[/dim]")
        return

    console.print()
    console.print(Rule("[dim]options[/dim]", style="dim"))

    skip_linter  = not Confirm.ask("[white]enable linter?[/white]",       default=True)
    skip_safety  = not Confirm.ask("[white]enable safety check?[/white]",  default=True)
    dry_run      =     Confirm.ask("[white]dry run (no api calls)?[/white]", default=False)
    model_override = None

    console.print()
    if Confirm.ask("[white]override primary model?[/white]", default=False):
        model_override = Prompt.ask("[dim]model id[/dim] [purple]▶[/purple]")

    console.print()
    console.print(Panel(
        f"[dim]path:[/dim]   [purple]{project_path}[/purple]\n"
        f"[dim]linter:[/dim]  {'[green]on[/green]' if not skip_linter else '[red]off[/red]'}\n"
        f"[dim]safety:[/dim]  {'[green]on[/green]' if not skip_safety else '[red]off[/red]'}\n"
        f"[dim]dry run:[/dim] {'[yellow]yes[/yellow]' if dry_run else '[green]no[/green]'}",
        title="[purple]configuration[/purple]",
        border_style="purple",
        box=box.ROUNDED,
    ))
    console.print()

    if not Confirm.ask("[purple]▶ start analysis?[/purple]", default=True):
        return

    run_pipeline(project_path, skip_linter, skip_safety, dry_run, model_override)


def run_pipeline(path, skip_linter, skip_safety, dry_run, model_override):
    clear()
    header()
    console.print(Rule("[dim]running pipeline[/dim]", style="purple"))
    console.print(f"[dim]main[/dim] / analyze / [purple]running[/purple]\n")

    cmd = [sys.executable, "main.py", "--project-path", path]
    if skip_linter:    cmd.append("--skip-linter")
    if skip_safety:    cmd.append("--skip-safety")
    if dry_run:        cmd.append("--dry-run")
    if model_override: cmd += ["--model", model_override]

    subprocess.run(cmd)

    console.print()
    console.print(Rule(style="purple"))
    Prompt.ask("\n[dim]press enter to return to main menu[/dim]")


def history_menu():
    clear()
    header()
    console.print(Rule("[dim]history[/dim]", style="purple"))
    console.print(f"[dim]main[/dim] / [purple]history[/purple]\n")

    import json, glob
    reports = sorted(glob.glob("./reports/*.md"), reverse=True)

    if not reports:
        console.print("[dim]no reports found yet.[/dim]")
    else:
        table = Table(box=box.SIMPLE, show_header=True, header_style="dim")
        table.add_column("date",   style="dim",    width=20)
        table.add_column("file",   style="purple")
        table.add_column("size",   style="dim", justify="right")

        for r in reports[:10]:
            stat = os.stat(r)
            mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            size  = f"{stat.st_size // 1024} KB"
            table.add_row(mtime, os.path.basename(r), size)

        console.print(table)

    console.print()
    Prompt.ask("[dim]press enter to go back[/dim]")


def model_config_menu():
    clear()
    header()
    console.print(Rule("[dim]model config[/dim]", style="purple"))
    console.print(f"[dim]main[/dim] / [purple]model config[/purple]\n")

    table = Table(box=box.SIMPLE, show_header=True, header_style="dim")
    table.add_column("step",  style="bold purple", width=6)
    table.add_column("role",  style="white",       width=24)
    table.add_column("model id", style="purple dim")

    models = [
        ("5A",  "coder agent",       os.getenv("MODEL_CODER",    "qwen/qwen3-coder-480b-a35b-instruct")),
        ("5B",  "reranker",          os.getenv("MODEL_RERANKER", "nvidia/llama-nemotron-rerank-1b-v2")),
        ("5C",  "report writer",     os.getenv("MODEL_REPORTER", "nvidia/llama-3.3-nemotron-super-49b-v1.5")),
        ("5D",  "safety validator",  os.getenv("MODEL_SAFETY",   "nvidia/nemotron-content-safety-reasoning-4b")),
        ("EMB", "embeddings",        os.getenv("MODEL_EMBED",    "nvidia/nv-embedcode-7b-v1")),
    ]

    for step, role, model in models:
        table.add_row(step, role, model)

    console.print(table)
    console.print("\n[dim]to change models, edit your .env:[/dim]")
    console.print("[purple dim]MODEL_CODER, MODEL_REPORTER, MODEL_RERANKER, MODEL_SAFETY, MODEL_EMBED[/purple dim]")
    console.print()
    Prompt.ask("[dim]press enter to go back[/dim]")


def main():
    while True:
        choice = main_menu()
        if   choice == "1": analyze_menu()
        elif choice == "2": history_menu()
        elif choice == "3": model_config_menu()
        elif choice == "4":
            clear()
            console.print("\n[purple]goodbye.[/purple]\n")
            sys.exit(0)


if __name__ == "__main__":
    main()
