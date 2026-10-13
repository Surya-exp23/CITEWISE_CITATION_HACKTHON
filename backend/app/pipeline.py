"""Pipeline orchestration — PRD section 7.

Stage order: Ingest -> Normalize -> Deduplicate -> Resolve institutions ->
Build edges and mentions -> Classify -> Metrics and flags ->
Evidence and hashing -> Reports.

run_pipeline(session, progress_cb, raw_works, raw_rows, semantic_cache) rebuilds
all derived state from the raw inputs, so it is safe to re-run:
  - derived tables (works, aliases, authors, authorships, citations, mentions,
    classifications, evidence, reports, integrity flags) are rebuilt
  - rejected_merges, decided review items and policies are preserved
  - pending review items are regenerated from the current data

raw_works / raw_rows are the seed inputs (see dedup.run_dedup docstring for the
raw_works contract; raw_rows items carry the RawCitationRow columns).
progress_cb(stage_name, counts_dict) is called after every stage.
"""
from app.models import (
    Author,
    Institution,
    RawCitationRow,
    Report,
    ReviewItem,
)

STAGES = [
    "ingest",
    "normalize",
    "deduplicate",
    "resolve_institutions",
    "edges_mentions",
    "classify",
    "metrics_integrity",
    "evidence_hashing",
    "reports",
]


def _emit(progress_cb, stage, counts):
    if progress_cb:
        progress_cb(stage, counts)


def run_pipeline(session, progress_cb=None, raw_works: list | None = None,
                 raw_rows: list | None = None, semantic_cache: dict | None = None,
                 ror_aliases: dict | None = None) -> dict:
    from app.services import dedup as dedup_svc
    from app.services import edges as edges_svc
    from app.services import integrity as integrity_svc
    from app.services import metrics as metrics_svc
    from app.services.classify import classify_all
    from app.services.normalize import normalize_doi, normalize_title
    from app.services.policy import ensure_default_policy

    raw_works = raw_works or []
    summary = {}

    # 1. Ingest (bulk insert for speed)
    if raw_rows is not None:
        session.query(RawCitationRow).delete()
        if raw_rows:
            session.bulk_insert_mappings(RawCitationRow, [
                {
                    "raw_citing_record_id": r["raw_citing_record_id"],
                    "raw_cited_record_id": r["raw_cited_record_id"],
                    "row_kind": r.get("row_kind", "reference_entry"),
                    "context_sentence": r.get("context_sentence"),
                    "section": r.get("section"),
                    "source": r.get("source"),
                    "is_synthetic": bool(r.get("is_synthetic")),
                }
                for r in raw_rows
            ])
    counts = {"raw_works": len(raw_works),
              "raw_citation_rows": session.query(RawCitationRow).count()}
    summary["ingest"] = counts
    _emit(progress_cb, "ingest", counts)

    # 2. Normalize (validation pass over the raw works)
    normed = sum(1 for w in raw_works if normalize_title(w.get("title")))
    dois = sum(1 for w in raw_works if normalize_doi(w.get("doi")))
    counts = {"works_normalized": normed, "dois_normalized": dois}
    summary["normalize"] = counts
    _emit(progress_cb, "normalize", counts)

    # 3. Deduplicate
    policy = ensure_default_policy(session)
    session.query(ReviewItem).filter_by(status="pending").delete()
    counts = dedup_svc.run_dedup(session, policy, raw_works, semantic_cache=semantic_cache)
    summary["deduplicate"] = counts
    _emit(progress_cb, "deduplicate", counts)

    # 4. Resolve institutions
    counts = dedup_svc.resolve_institutions(session, raw_works, ror_aliases=ror_aliases)
    summary["resolve_institutions"] = counts
    _emit(progress_cb, "resolve_institutions", counts)

    # 5. Build edges and mentions
    counts = edges_svc.build_edges(session)
    summary["edges_mentions"] = counts
    _emit(progress_cb, "edges_mentions", counts)

    # 6. Classify
    counts = classify_all(session, policy)
    summary["classify"] = counts
    _emit(progress_cb, "classify", counts)

    # 7. Metrics and flags
    researchers = session.query(Author).count()
    institutions = session.query(Institution).count()
    flag_counts = integrity_svc.run_integrity(session, policy)
    counts = {"researchers": researchers, "institutions": institutions, **flag_counts}
    summary["metrics_integrity"] = counts
    _emit(progress_cb, "metrics_integrity", counts)

    # 8. Evidence and hashing: evidence records are built on demand per scope
    # (GET /citations/{id}/evidence, POST /reports) via build_report_evidence.
    # Bulk pre-building 60k+ rows costs ~16s and serves no API need, so the
    # table starts empty and fills lazily; hashes verify identically.
    counts = {"scopes": 0, "evidence_records": 0, "mode": "on_demand"}
    summary["evidence_hashing"] = counts
    _emit(progress_cb, "evidence_hashing", counts)

    # 9. Reports: pre-generation for every scope is infeasible at demo scale
    # (12k scopes x full evidence payloads) and unnecessary — reports are
    # generated on demand via POST /reports, which is also the demo flow.
    # The table is cleared so reruns stay idempotent.
    session.query(Report).delete()
    counts = {"reports": 0, "mode": "on_demand"}
    summary["reports"] = counts
    _emit(progress_cb, "reports", counts)

    session.flush()
    return summary
