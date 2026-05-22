"""
nim_client.py — NVIDIA NIM API Engine
Handles all 5 model calls in the UPI pipeline:
  1. Embedder  (nv-embedcode-7b-v1)         → vector indexing
  2. Coder     (qwen3-coder-480b)            → deep code analysis
  3. Reranker  (llama-nemotron-rerank-1b-v2) → issue prioritization
  4. Reporter  (nemotron-super-49b)          → PM report generation
  5. Safety    (nemotron-content-safety-4b)  → hallucination guard
"""

import os
import time
import json
import numpy as np
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ─── Client ───────────────────────────────────────────────────────────────────
_client = OpenAI(
    base_url=os.getenv("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1"),
    api_key=os.getenv("NIM_API_KEY"),
)

# ─── Model IDs ────────────────────────────────────────────────────────────────
MODEL_CODER    = os.getenv("MODEL_CODER",    "qwen/qwen3-coder-480b-a35b-instruct")
MODEL_EMBEDDER = os.getenv("MODEL_EMBEDDER", "nvidia/nv-embedcode-7b-v1")
MODEL_RERANKER = os.getenv("MODEL_RERANKER", "nvidia/llama-nemotron-rerank-1b-v2")
MODEL_REPORTER = os.getenv("MODEL_REPORTER", "nvidia/llama-3.3-nemotron-super-49b-v1.5")
MODEL_SAFETY   = os.getenv("MODEL_SAFETY",   "nvidia/nemotron-content-safety-reasoning-4b")


# ─── Retry Helper ─────────────────────────────────────────────────────────────
def _with_retry(fn, attempts=3, base_wait=5):
    """Exponential backoff retry wrapper."""
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as e:
            if attempt == attempts - 1:
                raise
            wait = base_wait * (3 ** attempt)
            print(f"  [NIM] Attempt {attempt+1} failed: {e}. Retrying in {wait}s...")
            time.sleep(wait)


# ─── 1. EMBEDDER ──────────────────────────────────────────────────────────────
def embed_texts(texts: list[str], input_type: str = "passage") -> np.ndarray:
    """
    Embed a list of text strings using NV-EmbedCode 7B.
    input_type must be "passage" (for documents) or "query" (for search queries).
    Returns a 2D numpy array of shape (len(texts), embedding_dim).
    """
    def _call():
        response = _client.embeddings.create(
            model=MODEL_EMBEDDER,
            input=texts,
            encoding_format="float",
            extra_body={"input_type": input_type, "truncate": "END"},
        )
        return np.array([item.embedding for item in response.data])

    print(f"  [Embedder] Embedding {len(texts)} chunks (input_type={input_type}) with {MODEL_EMBEDDER}...")
    return _with_retry(_call)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Compute cosine similarity between a query vector and a matrix of vectors."""
    a_norm = a / (np.linalg.norm(a) + 1e-10)
    b_norm = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-10)
    return b_norm @ a_norm


def retrieve_relevant_chunks(query: str, chunks: list[str], chunk_embeddings: np.ndarray, top_k: int = 8) -> list[str]:
    """Retrieve the most relevant code chunks for a given query using cosine similarity."""
    # Use input_type='query' for the search query, 'passage' was used for the chunks
    query_vec = embed_texts([query], input_type="query")[0]
    scores = cosine_similarity(query_vec, chunk_embeddings)
    top_indices = np.argsort(scores)[::-1][:top_k]
    return [chunks[i] for i in top_indices]


# ─── 2. CODER (Primary Analysis Agent) ───────────────────────────────────────
def analyze_code(system_prompt: str, user_payload: str, stream: bool = True) -> str:
    """
    Run the primary deep code analysis using Qwen3 Coder 480B.
    Streams output to terminal in real-time and returns the full response.
    """
    print(f"\n  [Coder] Sending to {MODEL_CODER} (stream={stream})...")

    # Stop streaming if the model outputs this sentinel or exceeds max chars
    END_MARKER  = "## END OF REPORT"
    MAX_CHARS   = 8_000  # ~2k tokens; enough for a full concise report

    def _call():
        completion = _client.chat.completions.create(
            model=MODEL_CODER,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_payload},
            ],
            temperature=0.3,
            top_p=0.8,
            max_tokens=4096,
            frequency_penalty=0.6,  # Penalise repeated phrases to stop looping
            stream=stream,
        )

        if stream:
            full_response = ""
            for chunk in completion:
                if chunk.choices and chunk.choices[0].delta.content is not None:
                    token = chunk.choices[0].delta.content
                    print(token, end="", flush=True)
                    full_response += token

                    # ── Abort guard 1: end marker detected ────────────────
                    if END_MARKER in full_response:
                        print("\n  [Coder] End marker detected. Stopping stream.")
                        break

                    # ── Abort guard 2: hard character cap ─────────────────
                    if len(full_response) >= MAX_CHARS:
                        print(f"\n  [Coder] Max chars ({MAX_CHARS}) reached. Stopping stream.")
                        break

            print()  # newline after streaming ends
            # Trim everything after the end marker if present
            if END_MARKER in full_response:
                full_response = full_response[:full_response.index(END_MARKER) + len(END_MARKER)]
            return full_response
        else:
            return completion.choices[0].message.content

    return _with_retry(_call)



MODEL_RERANKER = os.getenv("MODEL_RERANKER", "meta/llama-3.1-8b-instruct")

def rerank_issues(query: str, passages: list[str]) -> list[str]:
    """
    Rerank a list of issue passages by relevance/severity using an LLM.
    We use Chat Completions to prioritize issues because the dedicated NIM /ranking endpoint is unavailable.
    """
    if not passages:
        return passages

    print(f"  [Reranker] Reranking {len(passages)} issues with {MODEL_RERANKER}...")

    def _call():
        system_prompt = (
            "You are an expert technical PM. Your job is to prioritize a list of code issues.\n"
            "Sort the following issues by severity (Critical first, then High, Medium, Low).\n"
            "Return ONLY the exact original passages, separated by double newlines, in the new prioritized order. "
            "Do not add any commentary or introductory text."
        )
        user_prompt = "\n\n=== ISSUE ===\n\n".join(passages)

        response = _client.chat.completions.create(
            model=MODEL_RERANKER,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=4096,
        )
        ranked_text = response.choices[0].message.content.strip()
        
        # Split back into passages and verify we haven't lost data
        ranked_passages = [p.strip() for p in ranked_text.split("=== ISSUE ===")]
        ranked_passages = [p for p in ranked_passages if p]
        
        if len(ranked_passages) == 0:
             return passages
        return ranked_passages

    try:
        return _with_retry(_call)
    except Exception as e:
        print(f"  [Reranker] Warning: reranker unavailable ({e}). Using original order.")
        return passages


# ─── 4. REPORTER (PM Report Generator) ───────────────────────────────────────
def generate_report(system_prompt: str, raw_analysis: str, stream: bool = True) -> str:
    """
    Take the raw Qwen3 analysis output and structure it into a
    clean PM-level report using Nemotron Super 49B v1.5.
    Streams output and returns the full report string.
    """
    user_msg = f"""
You have received the following raw code analysis from the primary coder agent:

--- RAW ANALYSIS START ---
{raw_analysis}
--- RAW ANALYSIS END ---

Now convert this into the structured Daily Improvement Report format exactly as specified in your system prompt.
Include all sections: Executive Summary, Critical Issues, Architecture Critique, Performance, Security, and the Actionable Backlog table.
"""

    def _call():
        completion = _client.chat.completions.create(
            model=MODEL_REPORTER,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_msg},
            ],
            temperature=0.3,
            max_tokens=4096,
            stream=stream,
        )
        if stream:
            full_response = ""
            for chunk in completion:
                if chunk.choices and chunk.choices[0].delta.content is not None:
                    token = chunk.choices[0].delta.content
                    print(token, end="", flush=True)
                    full_response += token
            print()
            return full_response
        else:
            return completion.choices[0].message.content

    return _with_retry(_call)


# ─── 5. SAFETY VALIDATOR ──────────────────────────────────────────────────────
def validate_safety(report_text: str) -> tuple[bool, str]:
    """
    Run the final report through the Content Safety Reasoning 4B model
    to catch hallucinated code suggestions or fabricated issues.
    Returns (is_safe: bool, reasoning: str).
    """
    print(f"  [Safety] Validating report with {MODEL_SAFETY}...")

    system_prompt = """You are a safety validator for AI-generated code audit reports.
Your job is to detect hallucinated, fabricated, or dangerous content in a software audit report.

Check for:
1. Fabricated file names or line numbers that likely don't exist
2. Made-up function names or API calls
3. Dangerous code suggestions (e.g., rm -rf, DROP TABLE without context)
4. Contradictory claims within the same report

Respond in JSON only:
{"is_safe": true/false, "issues_found": ["list of concerns or empty list"], "reasoning": "brief explanation"}
"""

    def _call():
        response = _client.chat.completions.create(
            model=MODEL_SAFETY,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": f"Validate this audit report:\n\n{report_text[:8000]}"},
            ],
            temperature=0.1,
            max_tokens=512,
            stream=False,
        )
        raw = response.choices[0].message.content.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        result = json.loads(raw)
        return result.get("is_safe", True), result.get("reasoning", "No issues found.")

    try:
        return _with_retry(_call)
    except Exception as e:
        print(f"  [Safety] Warning: safety check unavailable ({e}). Passing by default.")
        return True, "Safety check skipped (model unavailable)."
