"""Mention extraction helpers — PRD 11.5.

For the demo, mention rows come from raw rows carrying context sentences.
These helpers cover sentence splitting (pysbd) and the Europe PMC JATS
extraction pattern for future live ingest.
"""
import re

_segmenter = None


def _get_segmenter():
    global _segmenter
    if _segmenter is None:
        import pysbd

        _segmenter = pysbd.Segmenter(language="en", clean=False)
    return _segmenter


def split_sentences(text: str | None) -> list:
    """Split paragraph text into sentences with pysbd (fallback: regex)."""
    if not text:
        return []
    try:
        return [s.strip() for s in _get_segmenter().segment(text) if s.strip()]
    except Exception:
        return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def extract_mention_sentence(paragraph: str, window: int = 0) -> str | None:
    """Return the sentence containing a citation marker, e.g. '[12]'.

    window=0 keeps the exact sentence; window=1 includes one neighbour each side.
    """
    sentences = split_sentences(paragraph)
    hits = [i for i, s in enumerate(sentences) if re.search(r"\[\d+\]", s)]
    if not hits:
        return sentences[0] if sentences else None
    i = hits[0]
    lo, hi = max(0, i - window), min(len(sentences), i + window + 1)
    return " ".join(sentences[lo:hi])


def mention_from_raw_row(row_kind: str, context_sentence: str | None, section: str | None) -> dict | None:
    """Build a mention payload from one raw citation row. Returns None when the
    row carries no mention information."""
    if row_kind == "mention" or context_sentence:
        return {"sentence": context_sentence, "section": section}
    return None
