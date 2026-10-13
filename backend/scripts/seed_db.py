"""One-command demo bootstrap (idempotent).

    python scripts/seed_db.py

Loads data/demo/*.json, runs the full pipeline, and prints a stepper plus a
final summary with real researcher ids the UI can link to. Clears all tables
first, so re-running is safe. Must finish in under 30 seconds.

Speed strategy: the pipeline runs on an in-memory SQLite database (no I/O
stalls), then VACUUM INTO persists the result to the file DB the API serves.
"""
import os
import sys
import time

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings
from app.models import (  # noqa: F401  (imported for table clearing)
    Author,
    Authorship,
    Base,
    Citation,
    CitationClassification,
    Evidence,
    Institution,
    IntegrityFlag,
    Mention,
    Policy,
    RawCitationRow,
    RejectedMerge,
    Report,
    ReviewItem,
    Work,
    WorkAlias,
)
from app.pipeline import STAGES, run_pipeline
from app.services.demo_data import load_demo_dataset


def _db_path() -> str:
    url = settings.DATABASE_URL
    assert url.startswith("sqlite://"), "seed_db.py expects a sqlite DATABASE_URL"
    path = url[len("sqlite://"):]
    # sqlite:///./rel.db -> ./rel.db (CWD-relative); sqlite:////abs.db -> /abs.db
    if path.startswith("/./"):
        path = path[1:]
    return os.path.abspath(path)


def main() -> None:
    started = time.time()

    # In-memory engine for the pipeline; the file is written at the end.
    mem_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(mem_engine)
    session = sessionmaker(bind=mem_engine, expire_on_commit=False)()

    try:
        print("Loading demo dataset ...")
        raw_works, raw_rows, ror_aliases = load_demo_dataset()
        print(f"  raw works: {len(raw_works)}, raw citation rows: {len(raw_rows)}")

        order = {s: i + 1 for i, s in enumerate(STAGES)}

        def progress(stage: str, counts: dict):
            detail = ", ".join(f"{k}={v}" for k, v in counts.items())
            print(f"  [{order[stage]}/{len(STAGES)}] {stage}: {detail}")

        print("Running pipeline ...")
        summary = run_pipeline(session, progress_cb=progress, raw_works=raw_works,
                               raw_rows=raw_rows, ror_aliases=ror_aliases)
        session.commit()

        dedup = summary.get("deduplicate", {})
        print("\n--- summary ---")
        print(f"  works: {dedup.get('works')}, aliases: {dedup.get('aliases')}, "
              f"queued for review: {dedup.get('queued')}")
        print(f"  citations (edges): {summary.get('edges_mentions', {}).get('edges')}")
        print(f"  classification rows: {summary.get('classify', {}).get('rows')}")
        print(f"  reports: {summary.get('reports', {}).get('reports')}")

        # Real researcher ids for the frontend to link to (top by verified count).
        from sqlalchemy import func

        from app.models import CitationClassification
        from app.services.policy import ensure_default_policy

        policy = ensure_default_policy(session)
        verified_rows = (
            session.query(CitationClassification.scope_id,
                          func.count(CitationClassification.id))
            .filter(CitationClassification.scope_type == "researcher",
                    CitationClassification.klass == "external",
                    CitationClassification.policy_id == policy.id,
                    CitationClassification.policy_version == policy.version)
            .group_by(CitationClassification.scope_id)
            .order_by(func.count(CitationClassification.id).desc())
            .limit(8)
            .all()
        )
        unique_rows = dict(
            session.query(CitationClassification.scope_id,
                          func.count(CitationClassification.id))
            .filter(CitationClassification.scope_type == "researcher",
                    CitationClassification.scope_id.in_([r[0] for r in verified_rows] or [0]),
                    CitationClassification.policy_id == policy.id,
                    CitationClassification.policy_version == policy.version)
            .group_by(CitationClassification.scope_id)
            .all()
        )
        print("\n--- top researchers (for the UI) ---")
        for aid, verified in verified_rows:
            au = session.get(Author, aid)
            print(f"  /researchers/{aid}/report  {au.display_name} "
                  f"(verified={verified}, unique={unique_rows.get(aid, 0)})")

        aiims = session.query(Institution).filter(
            Institution.ror_id.like("%02dwcqs71")).first()
        if aiims:
            print(f"\n--- demo institution ---")
            print(f"  /institutions/{aiims.id}/report  {aiims.name}")

        # Persist the in-memory DB to the file the API serves.
        db_path = _db_path()
        if os.path.exists(db_path):
            os.remove(db_path)
        session.execute(text(f"VACUUM INTO '{db_path}'"))
        session.commit()
        print(f"\nWrote {db_path}")
        print(f"Done in {time.time() - started:.1f}s")
    finally:
        session.close()


if __name__ == "__main__":
    main()
