"""Evidence records and hashing — PRD section 11.9.

Hashing algorithm (must be byte-identical in any reimplementation, e.g. the
browser verifier on /verify):
  1. Canonical JSON: json.dumps(obj, sort_keys=True, separators=(",", ":"),
     ensure_ascii=False), encoded as UTF-8.
  2. Leaf hash = sha256(canonical_json).hexdigest().
  3. Leaves are sorted by citation_id ascending.
  4. Merkle root: repeatedly hash the concatenation of two adjacent hex
     strings with SHA-256 (concatenate the hex strings, encode as UTF-8,
     hash, hex-encode). If a level has an odd count, duplicate the last hash.
  5. root_hash is stored on the report and printed on the PDF; the QR code
     points at /verify/{report_id}.

Honest limitation (surface in UI/pitch): the hash proves a report was not
altered after generation and shows where each record came from. It does not
prove the upstream databases are correct — every record links to its DOI.
"""
import hashlib
import json
from datetime import datetime, timezone

from app.models import (
    Author,
    Authorship,
    Citation,
    Evidence,
    Institution,
    Mention,
    Report,
    Work,
)


def canonical_json(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def merkle_root(leaf_hexes: list) -> str:
    """Merkle root over leaf hashes already sorted by citation_id."""
    if not leaf_hexes:
        return sha256_hex("")
    level = list(leaf_hexes)
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        level = [sha256_hex(level[i] + level[i + 1]) for i in range(0, len(level), 2)]
    return level[0]


def build_evidence_record(*, citation_id: int, scope_type: str, scope_id: int,
                          citing: dict, cited: dict, mention_count: int,
                          raw_rows_total: int, duplicates_removed: int,
                          repeats_removed: int, klass: str, reason: dict,
                          policy_id: int | None, policy_version: int | None,
                          sources: list, context_sentences: list,
                          intent: str | None = None) -> dict:
    """Evidence record in the exact PRD 11.9 shape ('intent' is additive)."""
    return {
        "citation_id": citation_id,
        "scope": {"type": scope_type, "id": scope_id},
        "citing": {
            "doi": citing.get("doi"),
            "pmid": citing.get("pmid"),
            "title": citing.get("title"),
            "year": citing.get("year"),
            "authors": citing.get("authors", []),
            "institutions": citing.get("institutions", []),
        },
        "cited": {
            "doi": cited.get("doi"),
            "title": cited.get("title"),
            "year": cited.get("year"),
        },
        "mention_count": mention_count,
        "raw_rows_total": raw_rows_total,
        "duplicates_removed": duplicates_removed,
        "repeats_removed": repeats_removed,
        "class": klass,
        "intent": intent,
        "reason": reason,
        "policy": {"id": policy_id, "version": policy_version},
        "sources": sources,
        "links": {
            "citing": f"https://doi.org/{citing['doi']}" if citing.get("doi") else None,
            "cited": f"https://doi.org/{cited['doi']}" if cited.get("doi") else None,
        },
        "context_sentences": context_sentences,
    }


def _preload_work_info(session, work_ids: list) -> dict:
    """Work info dicts for many works via bulk queries.

    Output per work is identical to the original per-work _work_info.
    """
    if not work_ids:
        return {}
    works = {w.id: w for w in session.query(Work).filter(Work.id.in_(work_ids)).all()}
    # (work_id -> [(display_name, ror_id or None)]) ordered by authorship id.
    ah_rows = (
        session.query(Authorship.work_id, Author.display_name, Institution.ror_id)
        .join(Author, Authorship.author_id == Author.id)
        .outerjoin(Institution, Authorship.institution_id == Institution.id)
        .filter(Authorship.work_id.in_(work_ids))
        .order_by(Authorship.work_id, Authorship.id)
        .all()
    )
    grouped: dict = {}
    for wid, display_name, ror_id in ah_rows:
        grouped.setdefault(wid, []).append((display_name, ror_id))
    info = {}
    for wid in work_ids:
        w = works.get(wid)
        authors, institutions = [], []
        for display_name, ror_id in grouped.get(wid, []):
            authors.append(display_name)
            if ror_id:
                institutions.append(ror_id)
        info[wid] = {
            "doi": w.doi if w else None, "pmid": w.pmid if w else None,
            "title": w.title if w else None, "year": w.year if w else None,
            "authors": authors, "institutions": sorted(set(institutions)),
            "source": w.source if w else None,
        }
    return info


def build_report_evidence(session, scope_type: str, scope_id: int, policy) -> tuple:
    """Build evidence records for every citation in the scope, persist Evidence
    rows, and return (records_sorted_by_citation_id, merkle_root).

    Bulk-loaded: one query each for classifications, works, mentions; bulk
    Evidence inserts. Records and hashes are identical to the per-row version.
    """
    from app.models import CitationClassification
    from app.services.metrics import scope_citations

    session.query(Evidence).filter_by(scope_type=scope_type, scope_id=scope_id).delete()

    citations = sorted(scope_citations(session, scope_type, scope_id), key=lambda c: c.id)
    cit_ids = [c.id for c in citations]
    class_rows = {}
    if cit_ids:
        class_rows = {
            r.citation_id: r
            for r in session.query(CitationClassification).filter(
                CitationClassification.citation_id.in_(cit_ids),
                CitationClassification.scope_type == scope_type,
                CitationClassification.scope_id == scope_id,
                CitationClassification.policy_id == policy.id,
                CitationClassification.policy_version == policy.version,
            ).all()
        }
    work_ids = sorted({c.citing_work_id for c in citations}
                      | {c.cited_work_id for c in citations})
    work_info = _preload_work_info(session, work_ids)
    mentions_by_cit: dict = {}
    if cit_ids:
        for m in session.query(Mention).filter(
                Mention.citation_id.in_(cit_ids)).order_by(Mention.id).all():
            mentions_by_cit.setdefault(m.citation_id, []).append(m)

    records = []
    evidence_batch = []
    for cit in citations:
        cl = class_rows.get(cit.id)
        klass = cl.klass if cl else "external"
        reason = cl.reason if cl else {"rule": "unclassified"}
        citing = dict(work_info.get(cit.citing_work_id, {}))
        cited = dict(work_info.get(cit.cited_work_id, {}))
        sentences = [m.sentence for m in mentions_by_cit.get(cit.id, []) if m.sentence]
        sources = sorted({s for s in (citing.pop("source"), cited.pop("source")) if s})
        source_rows = [{"name": s, "retrieved_at": datetime.now(timezone.utc).isoformat()} for s in sources]
        record = build_evidence_record(
            citation_id=cit.id, scope_type=scope_type, scope_id=scope_id,
            citing=citing, cited=cited, mention_count=cit.mention_count,
            raw_rows_total=cit.raw_rows_total, duplicates_removed=cit.duplicates_removed,
            repeats_removed=cit.repeats_removed, klass=klass, reason=reason,
            policy_id=policy.id, policy_version=policy.version,
            sources=source_rows, context_sentences=sentences, intent=cit.intent,
        )
        leaf = sha256_hex(canonical_json(record))
        evidence_batch.append({"citation_id": cit.id, "scope_type": scope_type,
                               "scope_id": scope_id, "record": record, "sha256": leaf})
        records.append(record)
    if evidence_batch:
        session.bulk_insert_mappings(Evidence, evidence_batch)
    leaves = [sha256_hex(canonical_json(r)) for r in records]  # already citation_id order
    return records, merkle_root(leaves)


def verify_report_payload(payload: dict) -> dict:
    """Recompute leaf hashes and the Merkle root from a stored report payload."""
    records = sorted(payload.get("evidence", []), key=lambda r: r["citation_id"])
    leaves = [sha256_hex(canonical_json(r)) for r in records]
    recomputed = merkle_root(leaves)
    stored = payload.get("root_hash")
    return {
        "stored_root": stored,
        "recomputed_root": recomputed,
        "status": "MATCH" if stored == recomputed else "MISMATCH",
        "generated_at": payload.get("generated_at"),
        "record_count": len(records),
    }


def generate_report(session, scope_type: str, scope_id: int, policy, skip_evidence_build: bool = False) -> Report:
    """Generate and store a report row with payload + root hash (PRD 11.10).

    skip_evidence_build=True reuses Evidence rows already persisted for the
    scope (the pipeline builds them in the evidence stage); otherwise evidence
    is rebuilt here.
    """
    from app.services.integrity import detect_integrity_flags
    from app.services.metrics import (
        citation_timeline,
        institution_kpis,
        papers_table,
        researcher_kpis,
        top_citing_countries,
        top_citing_institutions,
    )
    from app.services.waterfall import build_waterfall

    if scope_type == "researcher":
        subject_row = session.get(Author, scope_id)
        rors = sorted({
            inst.ror_id for ah, inst in (
                session.query(Authorship, Institution)
                .join(Institution, Authorship.institution_id == Institution.id)
                .filter(Authorship.author_id == scope_id, Institution.ror_id.isnot(None))
                .all()
            ) if inst.ror_id
        })
        subject = {"id": subject_row.id, "name": subject_row.display_name,
                   "orcid": subject_row.orcid, "institutions": rors}
        kpis = researcher_kpis(session, scope_id, policy)
    elif scope_type == "institution":
        subject_row = session.get(Institution, scope_id)
        subject = {"id": subject_row.id, "name": subject_row.name, "ror": subject_row.ror_id}
        kpis = institution_kpis(session, scope_id, policy)
    else:
        raise ValueError(f"unknown scope_type: {scope_type}")

    waterfall = build_waterfall(
        raw_rows=kpis["raw_rows"],
        duplicates_removed=_waterfall_dedup(session, scope_type, scope_id),
        repeats_removed=_waterfall_repeats(session, scope_type, scope_id),
        unique_citations=kpis["unique_citations"],
        self_citations=kpis["self"],
        internal_citations=kpis["internal"],
        external_citations=kpis["external"],
        headline_metric=(policy.config or {}).get("headline_metric", "external_only"),
    )
    if skip_evidence_build:
        rows = (
            session.query(Evidence)
            .filter_by(scope_type=scope_type, scope_id=scope_id)
            .order_by(Evidence.citation_id)
            .all()
        )
        evidence_records = [r.record for r in rows]
        root = merkle_root([r.sha256 for r in rows])
    else:
        evidence_records, root = build_report_evidence(session, scope_type, scope_id, policy)

    synthetic_rows = (
        session.query(Citation).join(Mention, Mention.citation_id == Citation.id)
        .filter(Mention.is_synthetic.is_(True)).count()
    )
    payload = {
        "subject": subject,
        "scope_type": scope_type,
        "policy": {"id": policy.id, "version": policy.version,
                   "config": policy.config,
                   "headline_metric": (policy.config or {}).get("headline_metric")},
        "kpis": kpis,
        "waterfall": waterfall,
        "papers": papers_table(session, scope_type, scope_id, policy),
        "timeline": citation_timeline(session, scope_type, scope_id, policy),
        "top_citing_institutions": top_citing_institutions(session, scope_type, scope_id, policy),
        "top_citing_countries": top_citing_countries(session, scope_type, scope_id, policy),
        "integrity_flags": detect_integrity_flags(session, scope_type, scope_id, policy),
        "evidence": evidence_records,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_sources": ["OpenAlex (CC0)", "demo CSV / synthetic rows where flagged"],
        "data_notice": {"has_synthetic": synthetic_rows > 0, "synthetic_rows": synthetic_rows},
        "root_hash": root,
    }
    report = Report(scope_type=scope_type, scope_id=scope_id, policy_id=policy.id,
                    policy_version=policy.version, payload=payload, root_hash=root)
    session.add(report)
    session.flush()
    return report


def _waterfall_dedup(session, scope_type: str, scope_id: int) -> int:
    from app.services.metrics import scope_citations

    return sum(c.duplicates_removed or 0 for c in scope_citations(session, scope_type, scope_id))


def _waterfall_repeats(session, scope_type: str, scope_id: int) -> int:
    from app.services.metrics import scope_citations

    return sum(c.repeats_removed or 0 for c in scope_citations(session, scope_type, scope_id))
