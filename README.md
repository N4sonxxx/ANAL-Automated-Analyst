# Universal Project Improver (UPI)

A fully autonomous AI code auditor powered by a 5-model NVIDIA NIM pipeline. Point UPI at any software project, and it will analyze the codebase, detect bugs, critique the architecture, and generate a structured executive report.

## Features
- **Zero Config**: No project-specific setup required. Just point it at a folder.
- **5-Model Pipeline**: Uses Qwen3 Coder 480B, Nemotron Rerank 1B, Nemotron Super 49B, and Content Safety 4B.
- **Multi-Language**: Automatically detects Python, JS/TS, Go, Rust, Java, and C# projects.
- **Static Analysis**: Built-in support for ruff, pylint, and eslint.
- **Rich Interactive CLI**: Easy-to-use terminal interface.

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/N4sonxxx/Automated-Project-Reviewer.git
   cd Automated-Project-Reviewer
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   pip install rich
   ```

3. Create a `.env` file in the root directory and add your NVIDIA API key:
   ```env
   NIM_API_KEY=your_nvidia_api_key_here
   NIM_BASE_URL=https://integrate.api.nvidia.com/v1

   # Model IDs
   MODEL_CODER=qwen/qwen3-coder-480b-a35b-instruct
   MODEL_EMBEDDER=nvidia/nv-embedcode-7b-v1
   MODEL_RERANKER=nvidia/llama-nemotron-rerank-1b-v2
   MODEL_REPORTER=nvidia/llama-3.3-nemotron-super-49b-v1.5
   MODEL_SAFETY=nvidia/nemotron-content-safety-reasoning-4b
   ```

## Usage

Run the interactive CLI:
```bash
python cli.py
```

Alternatively, run the core pipeline directly:
```bash
# Full audit
python main.py --project-path "/path/to/project"

# Dry run (see context payload without API calls)
python main.py --project-path "/path/to/project" --dry-run
```

## How It Works
1. **Detect**: Fingerprints the project to find the language and framework.
2. **Harvest**: Gathers recent commits, hot files, and error logs.
3. **Lint**: Runs static analysis.
4. **Assemble**: Builds a comprehensive context payload.
5. **Analyze**: Qwen3 Coder finds issues.
6. **Rerank**: Nemotron prioritizes the findings.
7. **Report**: Nemotron Super structures the final Markdown report.
8. **Validate**: Content Safety model checks for hallucinations.
