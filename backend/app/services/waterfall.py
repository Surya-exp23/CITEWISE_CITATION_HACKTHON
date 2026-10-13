"""Raw-to-verified waterfall — PRD section 5.4.

Arithmetic:
    raw_rows - duplicates_removed - repeated_mentions == unique_citations
    unique_citations == self + internal + external
Both invariants are asserted; violations raise ValueError.
"""
HEADLINE_LABELS = {
    "external_only": "Verified external",
    "external_plus_internal": "Verified external + internal",
}


def build_waterfall(*, raw_rows: int, duplicates_removed: int, repeats_removed: int,
                    unique_citations: int, self_citations: int, internal_citations: int,
                    external_citations: int, headline_metric: str = "external_only") -> list:
    if raw_rows - duplicates_removed - repeats_removed != unique_citations:
        raise ValueError(
            f"waterfall invariant violated: {raw_rows} - {duplicates_removed} - "
            f"{repeats_removed} != {unique_citations}"
        )
    if unique_citations != self_citations + internal_citations + external_citations:
        raise ValueError(
            f"classification invariant violated: {unique_citations} != "
            f"{self_citations} + {internal_citations} + {external_citations}"
        )
    verified = external_citations + (internal_citations if headline_metric == "external_plus_internal" else 0)
    return [
        {"label": "Raw rows", "value": raw_rows},
        {"label": "Duplicate records removed", "value": -duplicates_removed},
        {"label": "Repeated mentions collapsed", "value": -repeats_removed},
        {"label": "Unique citations", "value": unique_citations, "subtotal": True},
        {"label": "Self-citations", "value": -self_citations},
        {"label": "Internal citations", "value": -internal_citations},
        {"label": HEADLINE_LABELS.get(headline_metric, "Verified external"),
         "value": verified, "total": True},
    ]
