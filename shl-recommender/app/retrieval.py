"""
retrieval.py
------------
Loads catalog.json, builds a FAISS vector index on first run,
and exposes search functions for the agent.

The index AND embedding model are cached in memory so they are
only built/loaded once at startup — never on every request.
"""

import json
import os
import threading
import numpy as np

_index       = None   # FAISS index
_catalog     = None   # list of all assessment dicts
_embeddings  = None   # numpy array of embeddings, shape (N, D)
_embed_model = None   # SentenceTransformer model (cached — do NOT reload per request)

CATALOG_PATH = os.path.join(os.path.dirname(__file__), "..", "catalog.json")

# ── test-type label lookup ────────────────────────────────────────────────────
TEST_TYPE_LABELS = {
    "A": "Ability & Aptitude",
    "B": "Biodata & Situational Judgement",
    "C": "Competencies",
    "D": "Development & 360",
    "E": "Assessment Exercises",
    "K": "Knowledge & Skills",
    "P": "Personality & Behavior",
    "S": "Simulations",
}


def _get_embed_model():
    """
    Return the cached SentenceTransformer model.
    Loads it once on first call. Never reloads.
    This is critical for performance — reloading on every request
    causes timeouts under the 30-second eval limit.
    """
    global _embed_model
    if _embed_model is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise ImportError(
                f"Missing library: {e}. "
                "Run: pip install sentence-transformers"
            ) from e
        print("[retrieval] Loading embedding model (one-time)…")
        # Using all-MiniLM-L6-v2: ~80MB, fits in Render free tier (512MB RAM).
        # all-mpnet-base-v2 has slightly better recall but is ~420MB and OOMs
        # on free hosting. The keyword boost in search() compensates well.
        _embed_model = SentenceTransformer("all-MiniLM-L6-v2")
        print("[retrieval] Embedding model loaded and cached.")
    return _embed_model


def _build_document(item: dict) -> str:
    """
    Combine all fields of a catalog item into a single rich text string
    for embedding. More context → better semantic search.
    """
    types_expanded = " ".join(
        TEST_TYPE_LABELS.get(t, t) for t in item.get("test_types", [])
    )
    # Name repeated twice so it anchors the embedding vector strongly.
    # Duration included so queries like "short test" match better.
    parts = [
        item.get("name", ""),
        item.get("name", ""),          # repeat for weight
        item.get("description", ""),
        types_expanded,
        "remote testing" if item.get("remote_testing") else "",
        "adaptive IRT computer adaptive" if item.get("adaptive_irt") else "",
        f"duration {item.get('duration_minutes', '')} minutes" if item.get("duration_minutes") else "",
    ]
    return " | ".join(p for p in parts if p).strip()


def _load_catalog() -> list[dict]:
    path = os.path.abspath(CATALOG_PATH)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"catalog.json not found at {path}. "
            "Run `python app/scraper.py` first."
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _build_index(catalog: list[dict]):
    """
    Embed all catalog items and build a FAISS flat inner-product index.
    Uses the cached SentenceTransformer — never reloads it.
    """
    try:
        import faiss
    except ImportError as e:
        raise ImportError(
            f"Missing library: {e}. "
            "Run: pip install faiss-cpu"
        ) from e

    model = _get_embed_model()

    documents = [_build_document(item) for item in catalog]
    print(f"[retrieval] Embedding {len(documents)} assessments…")
    embeddings = model.encode(
        documents,
        batch_size=32,
        show_progress_bar=True,
        normalize_embeddings=True,   # cosine similarity via dot product
    )

    # FAISS IndexFlatIP = inner product (= cosine when vectors are normalised)
    dim   = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings.astype(np.float32))

    print(f"[retrieval] Index built: {index.ntotal} vectors, dim={dim}")
    return index, embeddings


_init_lock = threading.Lock()   # prevents race between background thread and first request


def initialise():
    """
    Call once at startup to load catalog + build index.
    Thread-safe: uses a lock so background init and first /chat don't collide.
    """
    global _index, _catalog, _embeddings
    with _init_lock:
        if _index is not None:
            return   # already initialised

        _catalog    = _load_catalog()
        _index, _embeddings = _build_index(_catalog)


def _keyword_boost(query: str, items: list[dict], boost: float = 0.15) -> list[dict]:
    """
    Boost items whose name contains query keywords.
    This hybridises pure semantic search with keyword overlap,
    which significantly helps Recall@10 for role-specific queries
    like 'Java developer' or 'Python coding test'.

    Parameters
    ----------
    query : the user's search query
    items : list of catalog items already scored by FAISS
    boost : score increment per matching keyword hit

    Returns
    -------
    Re-sorted list with boosted scores.
    """
    # Only boost on meaningful words (length > 3 avoids noise like "and", "the")
    keywords = [w.lower() for w in query.split() if len(w) > 3]
    if not keywords:
        return items

    for item in items:
        name_lower = item["name"].lower()
        desc_lower = item.get("description", "").lower()
        # Count keyword hits across name (weighted more) and description
        name_hits = sum(1 for k in keywords if k in name_lower)
        desc_hits = sum(1 for k in keywords if k in desc_lower)
        item["_score"] = (
            item.get("_score", 0.0)
            + boost * name_hits          # name match is stronger signal
            + (boost * 0.5) * desc_hits  # description match is weaker
        )

    return sorted(items, key=lambda x: x.get("_score", 0.0), reverse=True)


def search(query: str, top_k: int = 15) -> list[dict]:
    """
    Semantic search over the SHL catalog, with keyword boosting.

    Parameters
    ----------
    query  : natural-language description of what's needed
    top_k  : max results to return (capped at len(catalog))

    Returns
    -------
    List of catalog dicts (same schema as catalog.json),
    ordered by relevance descending.
    """
    if _index is None:
        initialise()
    if not _catalog:
        return []

    model = _get_embed_model()
    q_emb = model.encode([query], normalize_embeddings=True).astype(np.float32)

    top_k = min(top_k, len(_catalog))
    scores, indices = _index.search(q_emb, top_k)

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx == -1:
            continue
        item = dict(_catalog[idx])   # shallow copy; don't mutate original
        item["_score"] = float(score)
        results.append(item)

    # FIX: apply keyword boost then re-sort for hybrid retrieval
    results = _keyword_boost(query, results)

    return results


def get_by_name(name: str) -> dict | None:
    """
    Look up a catalog item by name. Tries three strategies in order:
    1. Exact match
    2. Substring match (either direction)
    3. Word-level fuzzy match (requires >= 2 meaningful words to match)

    The >= 2 word requirement on fuzzy match (FIX from original) prevents
    single-word overlap from causing wrong matches — e.g. "Motivational
    Questionnaire" should NOT match "MQ Candidate Motivation Report" on
    just the word "motivation" alone, which caused Test 5 to fail.
    """
    if _catalog is None:
        initialise()

    name_lower = name.lower()

    # Strategy 1: exact match
    for item in _catalog:
        if item["name"].lower() == name_lower:
            return item

    # Strategy 2: substring match (either direction)
    for item in _catalog:
        item_name_lower = item["name"].lower()
        if name_lower in item_name_lower or item_name_lower in name_lower:
            return item

    # Strategy 3: word-level fuzzy — REQUIRE >= 2 words to match
    # FIX: was >= 1 word match which caused spurious matches (Test 5 bug)
    words = [w for w in name_lower.split() if len(w) > 3]
    if len(words) >= 2:   # only attempt fuzzy if there are enough query words
        for item in _catalog:
            item_lower = item["name"].lower()
            match_count = sum(1 for w in words if w in item_lower)
            if match_count >= 2:
                return item

    return None


def get_by_url(url: str) -> dict | None:
    """
    Look up a catalog item by its URL.
    Used for enriching LLM recommendations with correct catalog data.
    """
    if _catalog is None:
        initialise()
    for item in _catalog:
        if item["url"] == url:
            return item
    # Try with/without trailing slash
    url_alt = url.rstrip("/") + "/" if not url.endswith("/") else url.rstrip("/")
    for item in _catalog:
        if item["url"] == url_alt:
            return item
    return None


def get_all_catalog_urls() -> set[str]:
    """
    Returns a set of ALL URLs in the full catalog.
    Used for URL safety validation in the agent — must check against
    the full catalog, not just the top-K retrieved items.
    """
    if _catalog is None:
        initialise()
    return {item["url"] for item in _catalog}


def get_catalog_summary() -> str:
    """
    Returns a brief text summary of the catalog for use in the system prompt.
    Lists test type codes and total count.
    """
    if _catalog is None:
        initialise()
    return (
        f"The SHL catalog contains {len(_catalog)} Individual Test Solutions. "
        "Test types: A=Ability & Aptitude, B=Biodata & Situational Judgement, "
        "C=Competencies, D=Development & 360, E=Assessment Exercises, "
        "K=Knowledge & Skills, P=Personality & Behavior, S=Simulations."
    )


# NOTE: initialise() is called lazily by search() or by the background
# thread in main.py lifespan. Do NOT call it eagerly here — it blocks
# for ~3 minutes and prevents Render from detecting the open port.