# Approach Document: SHL Assessment Recommender

## 1. Design Choices
* **Framework:** Built using **FastAPI** for its high performance, ease of use, and native support for Pydantic validation, which ensures strict schema compliance on API inputs and outputs.
* **LLM Provider:** Used **Groq** with the `llama-3.3-70b-versatile` model. Groq offers extremely low latency, which is critical for meeting the 30-second timeout limit in the automated evaluator while still using a highly capable 70B parameter model that follows JSON schema instructions perfectly.
* **Architecture:** The application is entirely stateless. The `POST /chat` endpoint processes the full conversation history. State is intentionally not stored on the server to comply with the API specification.

## 2. Retrieval Setup
* **Vector Store & Embeddings:** Used **FAISS-CPU** alongside the `sentence-transformers` library. The catalog items are encoded at application startup to prevent cold-start delays during active requests.
* **Model Selection:** Initially tested with `all-mpnet-base-v2`, but it was too memory-intensive (~420MB) for free-tier hosting limits (e.g., Render's 512MB RAM). Switched to `all-MiniLM-L6-v2` (~80MB), which provides excellent semantic matching while comfortably fitting in low-memory environments.
* **Hybrid Search (Keyword Boosting):** Pure semantic search often struggles with highly specific queries (e.g., distinguishing "Java" from "JavaScript"). To solve this, a custom keyword-boosting algorithm was implemented. It calculates lexical overlap between the query and assessment names/descriptions and applies a multiplier to the FAISS cosine similarity score. This hybrid approach significantly improves `Recall@10`.
* **Deduplication & Comparison Handling:** If the user asks a comparison question ("compare OPQ and GSA"), regex extracts the acronyms and performs an exact/fuzzy name lookup first, ensuring the requested assessments are always injected into the LLM's context window.

## 3. Prompt Design & Agent Control
* **System Prompt:** The prompt strictly defines five operational modes: CLARIFY, RECOMMEND, REFINE, COMPARE, and REFUSE. The model is given a strict JSON schema template to follow.
* **Turn Limit Enforcement:** The prompt dynamically includes `{current_turn}` out of `{max_turns}` (8). When the conversation reaches turn 6 or higher, a `[SYSTEM OVERRIDE]` instruction is appended to the system prompt, forcing the LLM to output recommendations immediately rather than asking more clarifying questions.
* **Context Injection:** Up to 20 relevant catalog items are formatted into a dense text summary and injected into the prompt, giving the LLM ground-truth data to base its replies on.

## 4. Evaluation Approach & Verification
* **Local Test Suite:** Created `test_agent.py` to simulate the 6 primary test cases: vague queries (clarify), clear roles (recommend), immediate job descriptions (recommend), refinement (update shortlist), comparison, and off-topic rejection.
* **Post-Processing Validation:** To guarantee schema compliance and zero hallucinations, the LLM's output is programmatically intercepted before returning to the user:
  * **Enrichment:** Recommended URLs are matched against the loaded catalog. The `name` and `test_type` are forcefully overwritten by the true catalog data to eliminate LLM typos.
  * **URL Safety:** Any URL hallucinated by the model that does not exist in the catalog is stripped out.
  * **State Enforcement:** If `recommendations` is non-empty, `end_of_conversation` is hardcoded to `True`.
  * **Fallback:** If the turn limit is reached but the LLM still returns an empty list, the application falls back to returning the top 10 retrieved FAISS items to guarantee a score.

## 5. What Didn't Work & Improvements
* **Heavy Embeddings on Free Tiers:** As mentioned, `all-mpnet-base-v2` caused Out-Of-Memory (OOM) crashes on Render. Switching to `all-MiniLM-L6-v2` and augmenting it with keyword boosting achieved the same `Recall@10` at a fraction of the memory footprint.
* **Prompt-Only Constraints:** Initially, I relied solely on the prompt to enforce `end_of_conversation` and the 8-turn limit. The LLM would occasionally fail. Moving this logic to deterministic Python code (overriding outputs and injecting `[SYSTEM OVERRIDE]`) completely solved the issue, yielding a 100% pass rate in local tests.

## 6. AI Tool Usage
I utilized an AI coding assistant (Gemini/Antigravity) to perform static analysis on the codebase, debug environment encoding issues on Windows, generate the retrieval hybrid-search logic, and format the final deployment configuration (`render.yaml`, `Procfile`). The AI was primarily used for rapid refactoring and edge-case testing against the evaluator constraints.
