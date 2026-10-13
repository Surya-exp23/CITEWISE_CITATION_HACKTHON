"""Citation edge construction — PRD section 5.4.

Every raw_citation_rows row resolves to canonical work ids via work_aliases.
Rows group by (citing, cited) pair; per pair:
    raw_rows_total      = number of raw rows in the group
    rows_primary        = rows whose citing record is the canonical primary record
    duplicates_removed  = rows_total - rows_primary
    repeats_removed     = rows_primary - 1
Edge case: if the primary record contributed zero rows, rows_primary is treated
as 1 so the waterfall invariant raw - dup - rep == unique still holds (the one
counted citation is the canonical contribution; the rest are duplicates).

Mention rows come from raw rows with row_kind='mention' or a context sentence;
every citation gets at least one mention row (source 'reference_list' fallback).
"""
from collections import Counter

from app.models import Citation, Mention, RawCitationRow, WorkAlias
from app.services.intent import INTENT_PRIORITY, classify_intent
from app.services.mentions import mention_from_raw_row


def _aggregate_intent(intents: list) -> str:
    intents = [i for i in intents if i]
    if not intents:
        return "unclear"
    counts = Counter(intents)
    best = max(counts.values())
    for intent in INTENT_PRIORITY:
        if counts.get(intent) == best:
            return intent
    return "unclear"


def build_edges(session, progress_cb=None) -> dict:
    session.query(Mention).delete()
    session.query(Citation).delete()

    alias_rows = session.query(WorkAlias).all()
    rec2work = {a.raw_record_id: a.work_id for a in alias_rows}
    primary_of = {a.work_id: a.raw_record_id for a in alias_rows if a.merge_reason == "primary"}

    groups: dict = {}
    skipped_unresolved = 0
    skipped_self = 0
    for row in session.query(RawCitationRow).order_by(RawCitationRow.id).all():
        citing_id = rec2work.get(row.raw_citing_record_id)
        cited_id = rec2work.get(row.raw_cited_record_id)
        if citing_id is None or cited_id is None:
            skipped_unresolved += 1
            continue
        if citing_id == cited_id:
            skipped_self += 1
            continue
        groups.setdefault((citing_id, cited_id), []).append(row)

    for (citing_id, cited_id), rows in groups.items():
        primary_record = primary_of.get(citing_id)
        rows_total = len(rows)
        actual_primary = sum(1 for r in rows if r.raw_citing_record_id == primary_record)
        rows_primary = max(1, actual_primary)
        duplicates_removed = rows_total - rows_primary
        repeats_removed = rows_primary - 1

        citation = Citation(
            citing_work_id=citing_id,
            cited_work_id=cited_id,
            mention_count=0,
            raw_rows_total=rows_total,
            duplicates_removed=duplicates_removed,
            repeats_removed=repeats_removed,
        )
        session.add(citation)
        session.flush()

        intents = []
        n_mentions = 0
        for r in rows:
            payload = mention_from_raw_row(r.row_kind, r.context_sentence, r.section)
            if payload is None:
                continue
            intent = classify_intent([payload["sentence"]] if payload["sentence"] else [])
            intents.append(intent)
            session.add(Mention(
                citation_id=citation.id,
                sentence=payload["sentence"],
                section=payload["section"],
                source=r.source or "reference_list",
                is_synthetic=r.is_synthetic,
                intent=intent,
            ))
            n_mentions += 1
        if n_mentions == 0:
            src = rows[0]
            session.add(Mention(
                citation_id=citation.id,
                sentence=None,
                section=None,
                source="reference_list",
                is_synthetic=src.is_synthetic,
                intent="unclear",
            ))
            n_mentions = 1
            intents = ["unclear"]
        citation.mention_count = n_mentions
        citation.intent = _aggregate_intent(intents)

    session.flush()
    return {
        "edges": len(groups),
        "raw_rows_grouped": sum(len(v) for v in groups.values()),
        "skipped_unresolved": skipped_unresolved,
        "skipped_self_cite": skipped_self,
    }
