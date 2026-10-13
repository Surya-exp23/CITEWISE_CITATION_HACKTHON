"""T13: a rejected merge pair is never auto-merged on a rerun."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, RejectedMerge
from app.pipeline import run_pipeline
from conftest import _author, _work, work_id


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_t13_rejected_merge_stays_separate():
    works = [
        _work("M1", "Randomized trial of aspirin for stroke prevention",
              [_author("R Gupta", None, "first")], doi="10.1000/a1", year=2020),
        _work("M2", "Randomized trial of aspirin for stroke prevention",
              [_author("R Gupta", None, "first")], doi="10.1000/a2", year=2020),
    ]
    session = _session()
    run_pipeline(session, raw_works=works, raw_rows=[])
    session.commit()
    # Identical normalized titles merge on the first run.
    assert work_id(session, "M1") == work_id(session, "M2")

    # A human rejects the merge; rerunning must never re-merge the pair.
    session.add(RejectedMerge(raw_record_a="M1", raw_record_b="M2"))
    session.commit()
    run_pipeline(session, raw_works=works, raw_rows=[])
    session.commit()
    assert work_id(session, "M1") != work_id(session, "M2")
    session.close()
