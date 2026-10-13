"""T1–T5: normalization, dedup cascade, mention collapse."""
from app.models import Citation, ReviewItem, WorkAlias
from app.services.normalize import normalize_doi
from conftest import ROR_A, work_id


def test_t1_doi_normalization():
    assert normalize_doi("https://doi.org/10.1038/ABC") == normalize_doi("10.1038/abc")
    assert normalize_doi("doi:10.1038/abc.") == "10.1038/abc"


def test_t2_same_doi_merges_exact_id(db):
    # R2 carries the same DOI as R1 (different prefix/case/whitespace).
    assert work_id(db, "R1") == work_id(db, "R2")
    alias = db.query(WorkAlias).filter_by(raw_record_id="R2").one()
    assert alias.merge_reason == "exact_id"
    assert float(alias.merge_confidence) == 1.0


def test_t3_fuzzy_title_merges(db):
    # R3 is a spelling/punctuation variant of R1 with a shared author surname.
    assert work_id(db, "R1") == work_id(db, "R3")
    alias = db.query(WorkAlias).filter_by(raw_record_id="R3").one()
    assert alias.merge_reason == "fuzzy_title"


def test_t4_part_trap_never_merges_but_queues(db):
    # "Part 1" vs "Part 2" must never auto-merge; one review item is queued.
    assert work_id(db, "R4") != work_id(db, "R5")
    items = db.query(ReviewItem).filter_by(item_type="dedup", status="pending").all()
    pairs = {tuple(sorted([i.payload.get("record_a_id"), i.payload.get("record_b_id")])) for i in items}
    assert ("R4", "R5") in pairs


def test_t5_seven_mentions_collapse_to_one_citation(db):
    # C1 cites R1 in 7 rows: exactly 1 citation, mention_count=7, repeats_removed=6.
    citing = work_id(db, "C1")
    cited = work_id(db, "R1")
    cit = db.query(Citation).filter_by(citing_work_id=citing, cited_work_id=cited).one()
    assert cit.raw_rows_total == 7
    assert cit.duplicates_removed == 0
    assert cit.repeats_removed == 6
    assert cit.mention_count == 7
