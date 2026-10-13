"""T11 (waterfall invariants on the full demo) and T14 (pipeline vs ground_truth.json)."""
import json
import os

import pytest
from sqlalchemy import func

from app.models import (
    Author,
    Authorship,
    Citation,
    CitationClassification,
    WorkAlias,
)
from app.services.metrics import researcher_kpis

GT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "demo", "ground_truth.json")
AUTHORS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "demo", "authors.json")


def _gt():
    with open(GT_PATH, encoding="utf-8") as f:
        return json.load(f)


def _author_key_to_id(db):
    with open(AUTHORS_PATH, encoding="utf-8") as f:
        authors = json.load(f)
    by_openalex = {a.get("openalex_id"): a for a in authors if a.get("openalex_id")}
    by_name = {a["display_name"]: a for a in authors}
    mapping = {}
    for a in authors:
        au = None
        if a.get("openalex_id"):
            au = db.query(Author).filter_by(openalex_id=a["openalex_id"]).first()
        if au is None and a.get("display_name"):
            au = db.query(Author).filter_by(display_name=a["display_name"]).first()
        mapping[a["author_key"]] = au.id if au else None
    return mapping


def _classification_counts(db, policy, scope_type):
    rows = (
        db.query(CitationClassification.scope_id, CitationClassification.klass,
                 func.count(CitationClassification.id))
        .filter(CitationClassification.scope_type == scope_type,
                CitationClassification.policy_id == policy.id,
                CitationClassification.policy_version == policy.version)
        .group_by(CitationClassification.scope_id, CitationClassification.klass)
        .all()
    )
    out = {}
    for scope_id, klass, n in rows:
        out.setdefault(scope_id, {}).setdefault(klass, 0)
        out[scope_id][klass] += n
    return out


def test_t11_waterfall_invariants_every_scope(demo_db, demo_policy):
    """PRD 5.4 invariants via pure SQL aggregation (fast): for every researcher
    and every institution, raw - dup - rep == unique == self + internal + external."""
    db, policy = demo_db, demo_policy
    class_counts = {
        "researcher": _classification_counts(db, policy, "researcher"),
        "institution": _classification_counts(db, policy, "institution"),
    }

    # Researcher aggregation: one authorship per (author, work), so the join
    # does not duplicate citations.
    agg_rows = (
        db.query(Authorship.author_id,
                 func.sum(Citation.raw_rows_total),
                 func.sum(Citation.duplicates_removed),
                 func.sum(Citation.repeats_removed),
                 func.count(func.distinct(Citation.id)))
        .join(Citation, Citation.cited_work_id == Authorship.work_id)
        .group_by(Authorship.author_id)
        .all()
    )
    researcher_agg = {aid: [raw or 0, dup or 0, rep or 0, uniq or 0]
                      for aid, raw, dup, rep, uniq in agg_rows}

    # Institution aggregation: must dedupe citations across co-authors from the
    # same institution (summing per-author counts would double-count).
    inst_cits = (
        db.query(Authorship.institution_id, Citation.id,
                 Citation.raw_rows_total, Citation.duplicates_removed,
                 Citation.repeats_removed)
        .join(Citation, Citation.cited_work_id == Authorship.work_id)
        .filter(Authorship.institution_id.isnot(None))
        .distinct()
        .all()
    )
    institution_agg: dict = {}
    seen = set()
    for inst_id, cid, raw, dup, rep in inst_cits:
        if (inst_id, cid) in seen:
            continue
        seen.add((inst_id, cid))
        s = institution_agg.setdefault(inst_id, [0, 0, 0, 0])
        s[0] += raw or 0
        s[1] += dup or 0
        s[2] += rep or 0
        s[3] += 1

    checked = 0
    for scope_type, agg in (("researcher", researcher_agg), ("institution", institution_agg)):
        counts = class_counts[scope_type]
        for scope_id, (raw, dup, rep, unique) in agg.items():
            kl = counts.get(scope_id, {})
            total = kl.get("self", 0) + kl.get("internal", 0) + kl.get("external", 0)
            assert raw - dup - rep == unique, f"waterfall invariant failed for {scope_type} {scope_id}"
            assert total == unique, f"classification invariant failed for {scope_type} {scope_id}"
            checked += 1
    assert checked > 0


def test_t14_expected_merges(demo_db):
    db = demo_db
    gt = _gt()
    for entry in gt["expected_merges"]:
        a, b = entry["record_ids"]
        ra = db.query(WorkAlias).filter_by(raw_record_id=a).one()
        rb = db.query(WorkAlias).filter_by(raw_record_id=b).one()
        assert ra.work_id == rb.work_id, f"{a} and {b} should be merged"
        reasons = {ra.merge_reason, rb.merge_reason}
        assert entry["reason"] in reasons, f"{a}/{b}: expected {entry['reason']}, got {reasons}"


def test_t14_traps_not_merged(demo_db):
    db = demo_db
    for a, b in _gt()["traps_not_merged"]:
        ra = db.query(WorkAlias).filter_by(raw_record_id=a).one()
        rb = db.query(WorkAlias).filter_by(raw_record_id=b).one()
        assert ra.work_id != rb.work_id, f"trap pair {a}/{b} must never merge"


def test_t14_unique_citations_per_researcher(demo_db, demo_policy):
    db, policy = demo_db, demo_policy
    key_to_id = _author_key_to_id(db)
    for key, expected in _gt()["unique_citations_per_researcher"].items():
        author_db_id = key_to_id.get(key)
        assert author_db_id is not None, f"author key {key} not found in DB"
        kpis = researcher_kpis(db, author_db_id, policy)
        assert kpis["unique_citations"] == expected, (
            f"researcher {key}: expected {expected} unique citations, got {kpis['unique_citations']}")


def test_t14_sample_classifications(demo_db, demo_policy):
    db, policy = demo_db, demo_policy
    key_to_id = _author_key_to_id(db)
    rec2work = {a.raw_record_id: a.work_id for a in db.query(WorkAlias).all()}
    checked = 0
    for sample in _gt()["sample_classifications"]:
        citing = rec2work.get(sample["citing_record_id"])
        cited = rec2work.get(sample["cited_record_id"])
        scope_id = key_to_id.get(sample["researcher_key"])
        assert citing and cited and scope_id, f"unresolvable sample {sample}"
        cit = db.query(Citation).filter_by(citing_work_id=citing, cited_work_id=cited).one()
        row = db.query(CitationClassification).filter_by(
            citation_id=cit.id, scope_type="researcher", scope_id=scope_id,
            policy_id=policy.id, policy_version=policy.version).one()
        assert row.klass == sample["expected"], (
            f"{sample}: expected {sample['expected']}, got {row.klass}")
        checked += 1
    assert checked == len(_gt()["sample_classifications"])
