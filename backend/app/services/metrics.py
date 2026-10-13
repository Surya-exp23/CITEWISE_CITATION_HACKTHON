"""Metrics — PRD section 5.7.

h_index / i10_index are pure. KPI builders aggregate from
citation_classifications (SQL aggregation, no Python loops per citation).
"""
from app.models import (
    Author,
    Authorship,
    Citation,
    CitationClassification,
    Institution,
    Work,
)
from app.services.policy import policy_value


def h_index(counts: list) -> int:
    ranked = sorted((c for c in counts if c), reverse=True)
    h = 0
    for i, c in enumerate(ranked, start=1):
        if c >= i:
            h = i
        else:
            break
    return h


def i10_index(counts: list) -> int:
    return sum(1 for c in counts if c >= 10)


def scope_cited_work_ids(session, scope_type: str, scope_id: int) -> list:
    q = session.query(Work.id).join(Authorship, Authorship.work_id == Work.id)
    if scope_type == "researcher":
        q = q.filter(Authorship.author_id == scope_id)
    elif scope_type == "institution":
        q = q.filter(Authorship.institution_id == scope_id)
    else:
        raise ValueError(f"unknown scope_type: {scope_type}")
    return [r[0] for r in q.distinct().all()]


def scope_citations(session, scope_type: str, scope_id: int) -> list:
    work_ids = scope_cited_work_ids(session, scope_type, scope_id)
    if not work_ids:
        return []
    return session.query(Citation).filter(Citation.cited_work_id.in_(work_ids)).all()


def _class_map(session, citations: list, scope_type: str, scope_id: int, policy) -> dict:
    if not citations:
        return {}
    ids = [c.id for c in citations]
    rows = (
        session.query(CitationClassification.citation_id, CitationClassification.klass)
        .filter(
            CitationClassification.citation_id.in_(ids),
            CitationClassification.scope_type == scope_type,
            CitationClassification.scope_id == scope_id,
            CitationClassification.policy_id == policy.id,
            CitationClassification.policy_version == policy.version,
        )
        .all()
    )
    return {cid: klass for cid, klass in rows}


def _headline_counts(klass: str, headline_metric: str) -> bool:
    if headline_metric == "external_plus_internal":
        return klass in ("external", "internal")
    return klass == "external"


def scope_kpis(session, scope_type: str, scope_id: int, policy) -> dict:
    citations = scope_citations(session, scope_type, scope_id)
    class_map = _class_map(session, citations, scope_type, scope_id, policy)
    headline = policy_value(policy, "headline_metric", "external_only")

    counts = {"self": 0, "internal": 0, "external": 0}
    raw_rows = 0
    per_paper_raw: dict = {}
    per_paper_verified: dict = {}
    for cit in citations:
        klass = class_map.get(cit.id)
        if klass in counts:
            counts[klass] += 1
        raw_rows += cit.raw_rows_total or 0
        per_paper_raw[cit.cited_work_id] = per_paper_raw.get(cit.cited_work_id, 0) + (cit.raw_rows_total or 0)
        if klass and _headline_counts(klass, headline):
            per_paper_verified[cit.cited_work_id] = per_paper_verified.get(cit.cited_work_id, 0) + 1

    unique = len(citations)
    verified_total = sum(1 for cit in citations if _headline_counts(class_map.get(cit.id, ""), headline))
    return {
        "papers": len(scope_cited_work_ids(session, scope_type, scope_id)),
        "raw_rows": raw_rows,
        "unique_citations": unique,
        "self": counts["self"],
        "internal": counts["internal"],
        "external": counts["external"],
        "verified_total": verified_total,
        "h_index_raw": h_index(list(per_paper_raw.values())),
        "h_index_verified": h_index(list(per_paper_verified.values())),
        "i10_verified": i10_index(list(per_paper_verified.values())),
        "internal_ratio": round(counts["internal"] / unique, 4) if unique else 0.0,
        "self_ratio": round(counts["self"] / unique, 4) if unique else 0.0,
    }


def researcher_kpis(session, author_id: int, policy) -> dict:
    return scope_kpis(session, "researcher", author_id, policy)


def institution_kpis(session, institution_id: int, policy) -> dict:
    return scope_kpis(session, "institution", institution_id, policy)


def citation_timeline(session, scope_type: str, scope_id: int, policy) -> list:
    """Per-year external/internal/self counts (citing work year)."""
    citations = scope_citations(session, scope_type, scope_id)
    class_map = _class_map(session, citations, scope_type, scope_id, policy)
    work_year = {w.id: w.year for w in session.query(Work).all()}
    buckets: dict = {}
    for cit in citations:
        year = work_year.get(cit.citing_work_id)
        if year is None:
            continue
        b = buckets.setdefault(year, {"year": year, "external": 0, "internal": 0, "self": 0})
        klass = class_map.get(cit.id)
        if klass in b:
            b[klass] += 1
    return [buckets[y] for y in sorted(buckets)]


def _top_citing(session, scope_type: str, scope_id: int, policy, by: str, limit: int = 10) -> list:
    citations = scope_citations(session, scope_type, scope_id)
    if not citations:
        return []
    cit_ids = [c.id for c in citations]
    citing_ids = list({c.citing_work_id for c in citations})
    q = (
        session.query(Authorship, Institution)
        .join(Institution, Authorship.institution_id == Institution.id)
        .filter(Authorship.work_id.in_(citing_ids))
    )
    per_inst: dict = {}
    for ah, inst in q.all():
        key = inst.id
        entry = per_inst.setdefault(key, {"name": inst.name, "ror": inst.ror_id,
                                          "country": inst.country_code, "citations": set()})
        entry["citations"].add(ah.work_id)
    # map citing work -> citation ids for counting citations (not works)
    work_to_cits: dict = {}
    for c in citations:
        work_to_cits.setdefault(c.citing_work_id, set()).add(c.id)
    rows = []
    for entry in per_inst.values():
        cit_set = set()
        for ah_work_id in list(entry["citations"]):
            cit_set |= work_to_cits.get(ah_work_id, set())
        entry["count"] = len(cit_set)
        del entry["citations"]
        rows.append(entry)
    if by == "country":
        merged: dict = {}
        for r in rows:
            cc = r["country"] or "unknown"
            m = merged.setdefault(cc, {"country": cc, "count": 0})
            m["count"] += r["count"]
        rows = list(merged.values())
    rows.sort(key=lambda r: r["count"], reverse=True)
    return rows[:limit]


def top_citing_institutions(session, scope_type: str, scope_id: int, policy, limit: int = 10) -> list:
    return _top_citing(session, scope_type, scope_id, policy, by="institution", limit=limit)


def top_citing_countries(session, scope_type: str, scope_id: int, policy, limit: int = 10) -> list:
    return _top_citing(session, scope_type, scope_id, policy, by="country", limit=limit)


def papers_table(session, scope_type: str, scope_id: int, policy) -> list:
    """Per-paper rows for the report: raw/unique/self/internal/external/verified."""
    citations = scope_citations(session, scope_type, scope_id)
    class_map = _class_map(session, citations, scope_type, scope_id, policy)
    headline = policy_value(policy, "headline_metric", "external_only")
    work_ids = scope_cited_work_ids(session, scope_type, scope_id)
    works = {w.id: w for w in session.query(Work).filter(Work.id.in_(work_ids)).all()} if work_ids else {}
    per_paper: dict = {}
    for cit in citations:
        p = per_paper.setdefault(cit.cited_work_id, {"raw_rows": 0, "unique": 0, "self": 0,
                                                     "internal": 0, "external": 0, "verified": 0})
        p["raw_rows"] += cit.raw_rows_total or 0
        p["unique"] += 1
        klass = class_map.get(cit.id)
        if klass in p:
            p[klass] += 1
        if klass and _headline_counts(klass, headline):
            p["verified"] += 1
    rows = []
    for wid, p in per_paper.items():
        w = works.get(wid)
        rows.append({"work_id": wid, "title": w.title if w else "", "year": w.year if w else None,
                     "doi": w.doi if w else None, **p})
    rows.sort(key=lambda r: r["verified"], reverse=True)
    return rows


def leaderboard(session, policy, scope_type: str = "researcher", limit: int = 50,
                subject_ids: list | None = None) -> list:
    """Researcher leaderboard (raw vs verified columns)."""
    if scope_type == "researcher":
        q = session.query(Author).order_by(Author.id)
        if subject_ids is not None:
            q = q.filter(Author.id.in_(subject_ids))
        subjects = q.all()
    else:
        subjects = session.query(Institution).order_by(Institution.id).all()
    rows = []
    for s in subjects:
        kpis = scope_kpis(session, scope_type, s.id, policy)
        if kpis["papers"] == 0:
            continue
        name = s.display_name if scope_type == "researcher" else s.name
        rows.append({"id": s.id, "name": name, **kpis})
    rows.sort(key=lambda r: r["verified_total"], reverse=True)
    return rows[:limit]
