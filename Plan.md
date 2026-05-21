For that specific use case, here is the exact recommended stack:

---

## Primary Agent Model
```
Qwen3 Coder 480B
ID: qwen/qwen3-coder-480b-a35b-instruct
Why: Best agentic coding model in the catalog. Can scan 
     codebases, understand project structure, identify 
     issues, and generate optimized versions of code. 
     256K context = entire project in one pass.
```

---

## Supporting Stack
```
STEP 1 — Code Embedding / Indexing
Model: NV-EmbedCode 7B v1
ID: nvidia/nv-embedcode-7b-v1
Why: Purpose-built for code retrieval. Indexes every file 
     in the project folder into a searchable vector store 
     so the agent knows where everything is.

STEP 2 — Code Analysis + Review Generation
Model: Qwen3 Coder 480B
ID: qwen/qwen3-coder-480b-a35b-instruct
Why: Primary agent. Scans retrieved code chunks, identifies:
     - Anti-patterns
     - Security vulnerabilities
     - Performance bottlenecks
     - Architecture issues
     - Missing documentation
     Then generates the optimized version.

STEP 3 — Reranking (prioritize critical issues first)
Model: Llama Nemotron Rerank 1B v2
ID: nvidia/llama-nemotron-rerank-1b-v2
Why: Ranks the most critical issues to the top of 
     the report so the PM sees highest priority fixes first.

STEP 4 — Report Structuring + Summary
Model: Llama 3.3 Nemotron Super 49B v1.5
ID: nvidia/llama-3.3-nemotron-super-49b-v1.5
Why: Takes the raw analysis from Qwen3 Coder and turns 
     it into a clean, structured PM-level report with 
     executive summary, risk assessment, and action items.

STEP 5 — Safety / Hallucination Check
Model: Nemotron Content Safety Reasoning 4B
ID: nvidia/nemotron-content-safety-reasoning-4b
Why: Validates the report output before delivery, 
     ensures no hallucinated code suggestions or 
     fabricated issue descriptions pass through.
```

---

## Agent Workflow
```
project_folder/
       │
       ▼
[NV-EmbedCode 7B]          ← Scan + index all files
       │
       ▼
[Qwen3 Coder 480B]         ← Analyze + generate fixes
       │
       ▼
[Nemotron Rerank 1B v2]    ← Prioritize critical issues
       │
       ▼
[Nemotron Super 49B v1.5]  ← Generate PM report
       │
       ▼
[Content Safety 4B]        ← Validate output
       │
       ▼
FINAL REPORT OUTPUT:
  - Executive Summary
  - File-by-File Issues
  - Severity Rankings (Critical / High / Medium / Low)
  - Optimized Code Snippets
  - Architecture Recommendations
  - Estimated Refactor Effort
```

---

## Plain Text Model ID Reference
```
Primary Coder Agent
ID: qwen/qwen3-coder-480b-a35b-instruct

Code Embeddings
ID: nvidia/nv-embedcode-7b-v1

Reranker
ID: nvidia/llama-nemotron-rerank-1b-v2

Report Generator
ID: nvidia/llama-3.3-nemotron-super-49b-v1.5

Safety Validator
ID: nvidia/nemotron-content-safety-reasoning-4b
```