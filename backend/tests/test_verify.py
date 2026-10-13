"""T10 (tamper -> MISMATCH), T15 (independent reimplementation of the hash spec)."""
import hashlib
import json

from app.models import Evidence, Report
from app.services import evidence as ev
from app.services.evidence import generate_report, verify_report_payload
from conftest import author_id


def _independent_root_hash(records: list) -> str:
    """Plain reimplementation of the PRD 11.9 hashing spec — no ev.* helpers."""
    leaves = []
    for r in sorted(records, key=lambda x: x["citation_id"]):
        canonical = json.dumps(r, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=False).encode("utf-8")
        leaves.append(hashlib.sha256(canonical).hexdigest())
    level = list(leaves)
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        level = [hashlib.sha256((level[i] + level[i + 1]).encode("utf-8")).hexdigest()
                 for i in range(0, len(level), 2)]
    return level[0] if level else hashlib.sha256(b"").hexdigest()


def _report(db, policy):
    return generate_report(db, "researcher", author_id(db, "R Gupta"), policy)


def test_t10_match_then_mismatch_after_tamper(db, policy):
    report = _report(db, policy)
    db.commit()
    result = verify_report_payload(report.payload)
    assert result["status"] == "MATCH"
    assert result["stored_root"] == report.root_hash
    assert result["record_count"] > 0

    # Tamper with one evidence record and re-verify.
    tampered = json.loads(json.dumps(report.payload))
    tampered["evidence"][0]["class"] = "self"
    result = verify_report_payload(tampered)
    assert result["status"] == "MISMATCH"
    assert result["stored_root"] == report.root_hash


def test_t15_backend_hash_matches_independent_spec(db, policy):
    report = _report(db, policy)
    db.commit()
    records = report.payload["evidence"]
    assert _independent_root_hash(records) == report.root_hash
    # And every stored Evidence leaf equals the spec leaf.
    for ev_row in db.query(Evidence).filter(
            Evidence.scope_type == "researcher",
            Evidence.scope_id == author_id(db, "R Gupta")).all():
        canonical = json.dumps(ev_row.record, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=False).encode("utf-8")
        assert hashlib.sha256(canonical).hexdigest() == ev_row.sha256
