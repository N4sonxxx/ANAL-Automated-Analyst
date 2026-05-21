"""
main.py - Universal Project Improver (UPI) Orchestrator
=========================================================
The full 5-model pipeline:
  Step 1: project_detector  -> fingerprint the project
  Step 2: file_harvester    -> collect hot files, logs, git, configs
  Step 3: linter_runner     -> static analysis
  Step 4: context_builder   -> assemble NIM payload
  Step 5A: nim_client.analyze_code    -> Qwen3 Coder 480B (streaming)
  Step 5B: nim_client.rerank_issues   -> Nemotron Rerank 1B
  Step 5C: nim_client.generate_report -> Nemotron Super 49B (streaming)
  Step 5D: nim_client.validate_safety -> Content Safety 4B
  Step 6: reporter          -> save to target project

Usage:
  python main.py --project-path "C:/path/to/any/project"
  python main.py --project-path "C:/path/to/any/project" --dry-run
  python main.py --project-path "C:/path/to/any/project" --skip-linter --skip-safety
"""

import argparse
import sys
import os
from dotenv import load_dotenv

load_dotenv()

from scanner import project_detector, file_harvester, linter_runner
from core import context_builder, nim_client, reporter


BANNER = """
+----------------------------------------------------------+
|        Universal Project Improver (UPI) v1.0             |
|        Powered by NVIDIA NIM -- 5-Model Pipeline         |
+----------------------------------------------------------+
"""

SEP = "-" * 60


def main():
    print(BANNER)

    parser = argparse.ArgumentParser(
        description="Universal Project Improver - AI-powered codebase auditor"
    )
    parser.add_argument(
        "--project-path",
        required=True,
        help="Absolute path to the project folder you want to audit.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the assembled payload to terminal without saving files or calling the API.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override the primary coder model (default: qwen/qwen3-coder-480b-a35b-instruct).",
    )
    parser.add_argument(
        "--skip-linter",
        action="store_true",
        help="Skip the static analysis step.",
    )
    parser.add_argument(
        "--skip-safety",
        action="store_true",
        help="Skip the final safety validation step.",
    )

    args = parser.parse_args()

    project_path = os.path.abspath(args.project_path)
    if not os.path.isdir(project_path):
        print(f"  ERROR: Project path does not exist or is not a directory: {project_path}")
        sys.exit(1)

    print(f"  Target Project: {project_path}\n")

    # -- STEP 1: Project Detection -------------------------------------------
    print(SEP)
    print("  STEP 1/6 -- Project Detection")
    print(SEP)
    profile = project_detector.detect(project_path)

    # -- STEP 2: Content Harvesting ------------------------------------------
    print("\n" + SEP)
    print("  STEP 2/6 -- Content Harvesting")
    print(SEP)
    harvested = file_harvester.harvest(project_path, profile)

    # -- STEP 3: Static Analysis ---------------------------------------------
    print("\n" + SEP)
    print("  STEP 3/6 -- Static Analysis")
    print(SEP)
    if args.skip_linter:
        lint_output = "Static analysis skipped (--skip-linter flag set)."
        print("  [Linter] Skipped.")
    else:
        lint_output = linter_runner.run(project_path, profile)

    # -- STEP 4: Assemble Payload --------------------------------------------
    print("\n" + SEP)
    print("  STEP 4/6 -- Assembling NIM Payload")
    print(SEP)
    payload = context_builder.assemble(profile, harvested, lint_output)

    # -- DRY RUN: stop here --------------------------------------------------
    if args.dry_run:
        print("\n" + "=" * 60)
        print("  DRY RUN MODE -- Payload Preview (no API calls made)")
        print("=" * 60)
        preview = payload["user_payload"][:3000]
        print(preview)
        if len(payload["user_payload"]) > 3000:
            print(f"\n  ... [{len(payload['user_payload']) - 3000} more chars in full payload]")
        print(f"\n  Estimated tokens: ~{payload['estimated_tokens']:,}")
        print("  [Dry run complete. Re-run without --dry-run to execute the full pipeline.]")
        return

    # -- API key check -------------------------------------------------------
    if not os.getenv("NIM_API_KEY"):
        print("  ERROR: NIM_API_KEY not set. Add it to your .env file.")
        sys.exit(1)

    # -- STEP 5A: Qwen3 Coder 480B -- Deep Analysis (Streaming) -------------
    print("\n" + SEP)
    print("  STEP 5A/6 -- Qwen3 Coder 480B -- Deep Analysis (Streaming)")
    print(SEP)

    if args.model:
        os.environ["MODEL_CODER"] = args.model

    raw_analysis = nim_client.analyze_code(
        system_prompt=payload["coder_system_prompt"],
        user_payload=payload["user_payload"],
        stream=True,
    )

    # -- STEP 5B: Nemotron Rerank -- Issue Prioritization --------------------
    print("\n" + SEP)
    print("  STEP 5B/6 -- Nemotron Rerank -- Issue Prioritization")
    print(SEP)

    paragraphs = [p.strip() for p in raw_analysis.split("\n\n") if len(p.strip()) > 50]
    if len(paragraphs) > 1:
        ranked_paragraphs = nim_client.rerank_issues(
            query="critical bugs, security vulnerabilities, and high-priority performance issues",
            passages=paragraphs,
        )
        raw_analysis_ranked = "\n\n".join(ranked_paragraphs)
    else:
        raw_analysis_ranked = raw_analysis
        print("  [Reranker] Not enough paragraphs to rerank. Using original order.")

    # -- STEP 5C: Nemotron Super 49B -- Report Structuring (Streaming) -------
    print("\n" + SEP)
    print("  STEP 5C/6 -- Nemotron Super 49B -- Report Structuring (Streaming)")
    print(SEP)

    structured_report = nim_client.generate_report(
        system_prompt=payload["reporter_system_prompt"],
        raw_analysis=raw_analysis_ranked,
    )

    # -- STEP 5D: Content Safety 4B -- Hallucination Validation -------------
    print("\n" + SEP)
    print("  STEP 5D/6 -- Content Safety 4B -- Hallucination Validation")
    print(SEP)

    if args.skip_safety:
        is_safe, safety_note = True, "Safety check skipped (--skip-safety flag set)."
        print("  [Safety] Skipped.")
    else:
        is_safe, safety_note = nim_client.validate_safety(structured_report)
        status = "SAFE" if is_safe else "FLAGGED"
        print(f"  [Safety] Result: {status} -- {safety_note}")

    # -- STEP 6: Save Report -------------------------------------------------
    print("\n" + SEP)
    print("  STEP 6/6 -- Saving Report")
    print(SEP)

    report_path = reporter.save(
        report_text=structured_report,
        project_path=project_path,
        metadata=payload["metadata"],
        is_safe=is_safe,
        safety_note=safety_note,
    )

    reporter.print_summary(structured_report)
    print(f"  Done! Full report saved to:\n  {report_path}\n")


if __name__ == "__main__":
    main()
