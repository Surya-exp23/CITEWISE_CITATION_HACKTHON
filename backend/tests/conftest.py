"""Shared fixtures: in-memory SQLite sessions and hand-made mini datasets."""
import json
import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models import Base  # noqa: E402
from app.pipeline import run_pipeline  # noqa: E402
from app.services.demo_data import load_demo_dataset  # noqa: E402
from app.services.policy import ensure_default_policy  # noqa: E402

ROR_A = "https://ror.org/inst-a"
ROR_B = "https://ror.org/inst-b"
ROR_C = "https://ror.org/inst-c"


def _author(display_name, ror=None, position="first"):
    parts = display_name.split()
    last, first = parts[-1], parts[0]
    return {
        "openalex_id": None, "orcid": None, "display_name": display_name,
        "last_name": last, "first_name": first,
        "name_key": f"{last}_{first}".lower(),
        "position": position, "institution_ror": ror,
        "institution_name": ror, "country_code": None, "raw_affiliation": None,
    }


def _work(record_id, title, authors, doi=None, year=2020, extra=None):
    rec = {
        "record_id": record_id, "title": title, "doi": doi, "pmid": None, "pmcid": None,
        "year": year, "venue": None, "pub_type": "article", "is_preprint": False,
        "is_retracted": False, "mesh_terms": [], "source": "test", "retrieved_at": None,
        "is_synthetic": False, "openalex_id": None, "authors": authors,
    }
    if extra:
        rec.update(extra)
    return rec


def _row(citing, cited, kind="reference_entry", sentence=None, section=None):
    return {
        "raw_citing_record_id": citing, "raw_cited_record_id": cited, "row_kind": kind,
        "context_sentence": sentence, "section": section, "source": "test", "is_synthetic": False,
    }


@pytest.fixture
def mini_dataset():
    """Hand-made works + citation rows exercising T2–T9."""
    works = [
        _work("R1", "Effect of Metformin on Type 2 Diabetes: A Randomized Trial",
              [_author("R Gupta", ROR_A, "first"), _author("J Smith", ROR_B, "last")],
              doi="10.1000/met-a", year=2020),
        _work("R2", "Metformin trial results",
              [_author("R Gupta", ROR_A, "first")],
              doi="https://doi.org/10.1000/MET-A ", year=2020),  # same DOI -> exact_id
        _work("R3", "Effects of metformin on type-2 diabetes. A randomised trial.",
              [_author("R Gupta", ROR_A, "first")], year=2020),  # fuzzy -> merge
        _work("R4", "Cohort study of biomarkers: Part 1",
              [_author("M Khan", ROR_C, "first")], doi="10.1000/part1", year=2021),
        _work("R5", "Cohort study of biomarkers: Part 2",
              [_author("M Khan", ROR_C, "first")], doi="10.1000/part2", year=2021),
        _work("C1", "A review of diabetes therapies",
              [_author("J Smith", ROR_B, "first"), _author("M Khan", ROR_C, "last")],
              year=2022),
        _work("CSELF", "Gupta follow-up study",
              [_author("R Gupta", ROR_A, "first")], year=2022),
        _work("CINT", "Sharma extension cohort",
              [_author("A Sharma", ROR_A, "first"), _author("M Khan", ROR_C, "last")],
              year=2022),
        _work("CEXT", "Khan independent analysis",
              [_author("M Khan", ROR_C, "first"), _author("J Smith", ROR_B, "last")],
              year=2022),
        _work("CMID", "Smith multicenter paper",
              [_author("J Smith", ROR_B, "first"), _author("A Sharma", ROR_A, "middle"),
               _author("M Khan", ROR_C, "last")], year=2022),
    ]
    rows = [_row("C1", "R1", kind="mention",
                 sentence=f"Mention sentence number {i} about metformin [1].", section="Results")
            for i in range(7)]
    rows += [_row("CSELF", "R1"), _row("CINT", "R1"), _row("CEXT", "R1"), _row("CMID", "R1")]
    return works, rows


@pytest.fixture
def db(mini_dataset):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    works, rows = mini_dataset
    run_pipeline(session, raw_works=works, raw_rows=rows)
    session.commit()
    yield session
    session.close()


@pytest.fixture(scope="module")
def demo_db():
    """Full demo dataset pipeline, built once per module."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    raw_works, raw_rows, ror_aliases = load_demo_dataset()
    run_pipeline(session, raw_works=raw_works, raw_rows=raw_rows, ror_aliases=ror_aliases)
    session.commit()
    yield session
    session.close()


@pytest.fixture
def demo_policy(demo_db):
    return ensure_default_policy(demo_db)


@pytest.fixture
def policy(db):
    return ensure_default_policy(db)


def author_id(db, display_name: str) -> int:
    from app.models import Author

    return db.query(Author).filter_by(display_name=display_name).one().id


def work_id(db, raw_record_id: str) -> int:
    from app.models import WorkAlias

    return db.query(WorkAlias).filter_by(raw_record_id=raw_record_id).one().work_id


def ground_truth():
    here = os.path.dirname(__file__)
    with open(os.path.join(here, "..", "data", "demo", "ground_truth.json"), encoding="utf-8") as f:
        return json.load(f)
