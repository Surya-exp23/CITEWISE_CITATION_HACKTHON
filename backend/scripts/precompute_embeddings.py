"""Precompute embedding similarity scores for the offline demo.

Reads candidate title pairs (same first-author surname, year diff <= 1) from a
raw-works staging JSON, computes cosine similarities with all-MiniLM-L6-v2,
and writes data/cache/embeddings.json keyed by semantic.cache_key().

Run once with network access BEFORE the demo:
    python scripts/precompute_embeddings.py --from-staging data/staging/raw_works.json

Or with an explicit pairs file (JSON list of [title_a, title_b]):
    python scripts/precompute_embeddings.py --pairs pairs.json
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.normalize import normalize_name_part, normalize_title
from app.services.semantic import cache_key, pair_scores

OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "cache", "embeddings.json")


def pairs_from_staging(raw_works: list) -> list:
    titles = []
    for rw in raw_works:
        authors = rw.get("authors") or []
        surname = normalize_name_part((authors[0].get("last_name") if authors else "") or "")
        titles.append((normalize_title(rw.get("title")), rw.get("year"), surname))
    pairs = []
    seen = set()
    for i in range(len(titles)):
        for j in range(i + 1, len(titles)):
            ta, ya, sa = titles[i]
            tb, yb, sb = titles[j]
            if not ta or not tb or not sa or sa != sb:
                continue
            if ya is not None and yb is not None and abs(ya - yb) > 1:
                continue
            key = cache_key(ta, tb)
            if key not in seen:
                seen.add(key)
                pairs.append((ta, tb))
    return pairs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-staging", default=None, help="raw_works staging JSON")
    ap.add_argument("--pairs", default=None, help="JSON list of [title_a, title_b]")
    ap.add_argument("--out", default=OUT_PATH)
    args = ap.parse_args()

    if args.pairs:
        with open(args.pairs, encoding="utf-8") as fh:
            pairs = [tuple(p) for p in json.load(fh)]
    elif args.from_staging:
        with open(args.from_staging, encoding="utf-8") as fh:
            pairs = pairs_from_staging(json.load(fh))
    else:
        ap.error("provide --from-staging or --pairs")

    print(f"computing embeddings for {len(pairs)} pairs ...")
    scores = pair_scores(pairs)
    if not scores:
        print("model unavailable — nothing written. Install sentence-transformers + torch and retry.")
        sys.exit(1)
    out = {}
    for (a, b), score in scores.items():
        out[cache_key(normalize_title(a), normalize_title(b))] = round(score, 4)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh)
    print(f"wrote {len(out)} scores to {args.out}")


if __name__ == "__main__":
    main()
