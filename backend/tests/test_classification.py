"""T6–T9: classification (self / internal / external) and the policy flip."""
from app.models import Citation, CitationClassification
from app.services.policy import update_policy
from conftest import ROR_A, author_id, work_id


def _class(db, policy, citing_rec, cited_rec, scope_type="researcher", scope_id=None):
    citing = work_id(db, citing_rec)
    cited = work_id(db, cited_rec)
    cit = db.query(Citation).filter_by(citing_work_id=citing, cited_work_id=cited).one()
    if scope_id is None:
        scope_id = author_id(db, "R Gupta")
    return db.query(CitationClassification).filter_by(
        citation_id=cit.id, scope_type=scope_type, scope_id=scope_id,
        policy_id=policy.id, policy_version=policy.version).one()


def test_t6_self_citation(db, policy):
    gupta = author_id(db, "R Gupta")
    row = _class(db, policy, "CSELF", "R1", scope_id=gupta)
    assert row.klass == "self"


def test_t7_internal_citation_names_ror(db, policy):
    gupta = author_id(db, "R Gupta")
    row = _class(db, policy, "CINT", "R1", scope_id=gupta)
    assert row.klass == "internal"
    assert (row.reason or {}).get("matched_ror") == ROR_A


def test_t8_external_citation(db, policy):
    gupta = author_id(db, "R Gupta")
    row = _class(db, policy, "CEXT", "R1", scope_id=gupta)
    assert row.klass == "external"


def test_t9_policy_flip_first_last(db, policy):
    gupta = author_id(db, "R Gupta")
    # CMID shares an institution (ROR_A) only via middle author A. Sharma.
    before = _class(db, policy, "CMID", "R1", scope_id=gupta)
    assert before.klass == "internal"
    update_policy(db, policy.id, {"citing_authors_considered": "first_last"})
    db.commit()
    after = _class(db, policy, "CMID", "R1", scope_id=gupta)
    assert after.klass == "external"


def test_t10_create_policy_classifies_and_activates(db, policy):
    from app.models import Policy
    from app.services.policy import create_policy, get_active_policy
    from app.services.report_view import researcher_report

    new = create_policy(db, name="jury demo",
                        config={"citing_authors_considered": "first_last"})
    db.commit()
    assert get_active_policy(db).id == new.id
    assert db.query(Policy).filter_by(is_active=True).count() == 1
    rows = db.query(CitationClassification).filter_by(
        policy_id=new.id, policy_version=new.version).count()
    assert rows > 0
    gupta = author_id(db, "R Gupta")
    rep = researcher_report(db, gupta, new.id)
    assert rep["policy"]["id"] == new.id
    assert rep["kpis"]["unique_citations"] > 0
