"""Embedding-based title similarity — AI module (L3b dedup signal).

Uses sentence-transformers (all-MiniLM-L6-v2). Degrades gracefully: if the
model cannot be imported or loaded (no torch, no network), every function
returns an empty result and the pipeline simply skips the semantic signal.

For the offline demo, run scripts/precompute_embeddings.py once (with
network) to write data/cache/embeddings.json; dedup then consults that cache
with no model needed.
"""
import hashlib
import json
import os

MODEL_NAME = "all-MiniLM-L6-v2"
CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "cache", "embeddings.json")

_model = None


def cache_key(title_a_norm: str, title_b_norm: str) -> str:
    """Stable cache key for a normalized title pair (order-independent)."""
    a, b = sorted([title_a_norm or "", title_b_norm or ""])
    return hashlib.sha256(f"{a}|{b}".encode("utf-8")).hexdigest()


def _load_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(MODEL_NAME)
    return _model


def pair_scores(pairs: list) -> dict:
    """Cosine similarity per title pair. Returns {} when the model is
    unavailable — the caller must treat this as 'no signal', never as zero."""
    if not pairs:
        return {}
    try:
        model = _load_model()
    except Exception:
        return {}
    try:
        import numpy as np

        unique = list(dict.fromkeys(t for pair in pairs for t in pair))
        embeddings = model.encode(unique, normalize_embeddings=True, show_progress_bar=False)
        sims = np.dot(embeddings, embeddings.T)
        idx = {t: i for i, t in enumerate(unique)}
        return {(a, b): float(sims[idx[a], idx[b]]) for a, b in pairs}
    except Exception:
        return {}


def semantic_scores(pairs: list) -> dict:
    """pairs: list of (title_a, title_b).

    Returns {(i, j): cosine_similarity} where i, j are the indices of the two
    titles in the deduplicated title list (order of first appearance).
    Returns {} when the model is unavailable.
    """
    scores = pair_scores(pairs)
    if not scores:
        return {}
    unique = list(dict.fromkeys(t for pair in pairs for t in pair))
    idx = {t: i for i, t in enumerate(unique)}
    return {(idx[a], idx[b]): s for (a, b), s in scores.items()}


def load_cached_scores(path: str | None = None) -> dict:
    """Load precomputed {cache_key: score} pairs for offline use."""
    path = path or CACHE_PATH
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return {str(k): float(v) for k, v in data.items()}
    except Exception:
        return {}
