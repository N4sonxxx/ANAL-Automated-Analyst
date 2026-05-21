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
def embed_texts(texts: list[str]) -> np.ndarray:
    """
    Embed a list of text strings using NV-EmbedCode 7B.
    Returns a 2D numpy array of shape (len(texts), embedding_dim).
    """
    def _call():
        response = _client.embeddings.create(
            model=MODEL_EMBEDDER,
            input=texts,
            encoding_format="float",
        )
        return np.array([item.embedding for item in response.data])

    print(f"  [Embedder] Embedding {len(texts)} chunks with {MODEL_EMBEDDER}...")
    return _with_retry(_call)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Compute cosine similarity between a query vector and a matrix of vectors."""
    a_norm = a / (np.linalg.norm(a) + 1e-10)
    b_norm = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-10)
    return b_norm @ a_norm


def retrieve_relevant_chunks(query: str, chunks: list[str], chunk_embeddings: np.ndarray, top_k: int = 8) -> list[str]:
    """Retrieve the most relevant code chunks for a given query using cosine similarity."""
    query_vec = embed_texts([query])[0]
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

    def _call():
        completion = _client.chat.completions.create(
            model=MODEL_CODER,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_payload},
            ],
            temperature=0.7,
            top_p=0.8,
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
            print()  # newline after streaming ends
            return full_response
        else:
            return completion.choices[0].message.content

    return _with_retry(_call)


# ─── 3. RERANKER ──────────────────────────────────────────────────────────────
def rerank_issues(query: str, passages: list[str]) -> list[str]:
    """
    Rerank a list of issue passages by relevance/severity using
    Llama Nemotron Rerank 1B v2.
    Returns passages sorted from most to least critical.
    """
    if not passages:
        return passages

    print(f"  [Reranker] Reranking {len(passages)} issues with {MODEL_RERANKER}...")

    def _call():
        # NIM reranker uses the /v1/ranking endpoint via raw HTTP
        # We access it through the client's underlying httpx client
        payload = {
            "model": MODEL_RERANKER,
            "query": {"text": query},
            "passages": [{"text": p} for p in passages],
        }
        response = _client._client.post(
            "/ranking",
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

        # The response contains rankings with logit scores
        rankings = data.get("rankings", [])
        # Sort passages by score descending
        scored = sorted(
            [(r["index"], r["logit"]) for r in rankings],
            key=lambda x: x[1],
            reverse=True,
        )
        return [passages[i] for i, _ in scored]

    try:
        return _with_retry(_call)
    except Exception as e:
        print(f"  [Reranker] Warning: reranker unavailable ({e}). Using original order.")
        return passages


# ─── 4. REPORTER (PM Report Generator) ───────────────────────────────────────
def generate_report(system_prompt: str, raw_analysis: str) -> str:
    """
    Take the raw Qwen3 analysis output and structure it into a
    clean PM-level report using Nemotron Super 49B v1.5.
    Streams output and returns the full report string.
    """
    print(f"\n  [Reporter] Structuring report with {MODEL_REPORTER}...")

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
            stream=True,
        )
        full_response = ""
        for chunk in completion:
            if chunk.choices and chunk.choices[0].delta.content is not None:
                token = chunk.choices[0].delta.content
                print(token, end="", flush=True)
                full_response += token
        print()
        return full_response

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
