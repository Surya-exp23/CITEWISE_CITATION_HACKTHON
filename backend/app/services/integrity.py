"""Integrity flags — PRD section 5.8.

Flags are signals, not accusations: wording stays neutral ("worth reviewing").
Each flag carries evidence ids for drill-down. detect_integrity_flags is
scope-aware; run_integrity computes and persists flags for all researchers
and institutions.
"""
import networkx as nx

from app.models import (
    Author,
    Authorship,
    Citation,
    CitationClassification,
    IntegrityFlag,
    Institution,
    Work,
)
from app.services.metrics import scope_citations, scope_kpis
from app.services.policy import policy_value


def _author_node_key(author: Author) -> str:
    return author.openalex_id or author.orcid or f"name:{author.name_key}"


def _compute_flags(*, scope_type: str, scope_id: int, policy,
                   unique: int, internal_ratio: float,
                   citations: list, work_author_keys: dict,
                   retracted: dict, ring_members: set | None,
                   ring_works: set | None = None) -> list:
    """Pure flag computation over preloaded plain data.

    citations: [(citation_id, citing_work_id, cited_work_id), ...] in scope order.
    work_author_keys: {work_id: [(author_node_key, display_name), ...]} ordered
    by authorship id. retracted: {work_id: bool}. Rules, thresholds and details
    are identical to the original per-row implementation.
    """
    flags = []

    if scope_type == "researcher":
        # cites_retracted: a retracted paper cites the researcher's work, or the
        # researcher's own paper is retracted.
        retracted_citing = [cid for cid, citing_wid, _ in citations
                            if retracted.get(citing_wid)]
        own_retracted = [cited_wid for _, _, cited_wid in citations
                         if retracted.get(cited_wid)]
        if retracted_citing or own_retracted:
            flags.append({
                "flag_type": "cites_retracted",
                "scope_type": scope_type, "scope_id": scope_id,
                "severity": "review",
                "details": {
                    "note": "Retracted papers appear in this citation record \u2014 worth reviewing.",
                    "retracted_citing_citation_ids": sorted(set(retracted_citing)),
                    "retracted_own_work_ids": sorted(set(own_retracted)),
                },
            })

    threshold = policy_value(policy, "internal_ratio_flag_threshold", 0.5)
    if unique >= 10 and internal_ratio >= threshold:
        flags.append({
            "flag_type": "high_internal_ratio",
            "scope_type": scope_type, "scope_id": scope_id,
            "severity": "review",
            "details": {
                "note": "A high share of citations comes from the same institution \u2014 worth reviewing.",
                "internal_ratio": internal_ratio,
                "threshold": threshold,
                "unique_citations": unique,
            },
        })

    # citation_concentration: top-3 citing authors' share of unique citations.
    if unique:
        citing_author_counts: dict = {}
        citing_author_names: dict = {}
        for _, citing_wid, _ in citations:
            for key, display_name in work_author_keys.get(citing_wid, []):
                citing_author_counts[key] = citing_author_counts.get(key, 0) + 1
                citing_author_names[key] = display_name
        top3 = sorted(citing_author_counts.values(), reverse=True)[:3]
        concentration = sum(top3) / unique
        conc_threshold = policy_value(policy, "concentration_flag_threshold", 0.4)
        if concentration >= conc_threshold:
            top_names = [citing_author_names[k] for k, _ in
                         sorted(citing_author_counts.items(), key=lambda kv: kv[1], reverse=True)[:3]]
            flags.append({
                "flag_type": "citation_concentration",
                "scope_type": scope_type, "scope_id": scope_id,
                "severity": "review",
                "details": {
                    "note": "A small number of citing authors accounts for a large share of citations \u2014 worth reviewing.",
                    "concentration": round(concentration, 4),
                    "threshold": conc_threshold,
                    "top_citing_authors": top_names,
                },
            })

    # citation_ring membership (rings detected globally). Fast path: only
    # enumerate author keys when the scope touches a work with a ring member.
    if ring_members:
        scope_wids = {wid for _, citing_wid, cited_wid in citations
                      for wid in (citing_wid, cited_wid)}
        hit = []
        if scope_wids & ring_works:
            scope_author_keys = set()
            for wid in scope_wids:
                for key, _name in work_author_keys.get(wid, []):
                    scope_author_keys.add(key)
            hit = sorted(scope_author_keys & ring_members)
        if hit:
            flags.append({
                "flag_type": "citation_ring",
                "scope_type": scope_type, "scope_id": scope_id,
                "severity": "review",
                "details": {
                    "note": "These authors appear in a dense mutual-citation group \u2014 worth reviewing, not an accusation.",
                    "ring_author_keys": hit,
                },
            })
    return flags


def _node_key(openalex_id, orcid, name_key) -> str:
    return openalex_id or orcid or f"name:{name_key}"


def detect_integrity_flags(session, scope_type: str, scope_id: int, policy,
                           ring_members: set | None = None) -> list:
    """Flags for one scope. ring_members: author node keys in a detected ring
    (computed globally by detect_citation_rings)."""
    kpis = scope_kpis(session, scope_type, scope_id, policy)
    unique = kpis["unique_citations"]
    citations = scope_citations(session, scope_type, scope_id)

    work_ids = sorted({c.citing_work_id for c in citations}
                      | {c.cited_work_id for c in citations})
    retracted: dict = {}
    work_author_keys: dict = {}
    if work_ids:
        for wid, is_r in session.query(Work.id, Work.is_retracted).filter(
                Work.id.in_(work_ids)).all():
            retracted[wid] = bool(is_r)
        for wid, oa_id, orcid, name_key, display_name in (
            session.query(Authorship.work_id, Author.openalex_id, Author.orcid,
                          Author.name_key, Author.display_name)
            .join(Author, Authorship.author_id == Author.id)
            .filter(Authorship.work_id.in_(work_ids))
            .order_by(Authorship.work_id, Authorship.id)
            .all()
        ):
            work_author_keys.setdefault(wid, []).append(
                (_node_key(oa_id, orcid, name_key), display_name))

    return _compute_flags(
        scope_type=scope_type, scope_id=scope_id, policy=policy,
        unique=unique, internal_ratio=kpis["internal_ratio"],
        citations=[(c.id, c.citing_work_id, c.cited_work_id) for c in citations],
        work_author_keys=work_author_keys, retracted=retracted,
        ring_members=ring_members,
    )


def _rings_from_preloaded(work_keys: dict, cit_pairs: list, k: int) -> list:
    """Ring detection core: takes per-work author node-key lists and
    (citing_work_id, cited_work_id) pairs. Shared by detect_citation_rings and
    run_integrity so the preload queries run once."""
    # Accumulate edge weights in a plain dict (same graph as the original
    # per-pair networkx updates, without the per-pair lookup overhead).
    weights: dict = {}
    for citing_wid, cited_wid in cit_pairs:
        citing_keys = work_keys.get(citing_wid, ())
        cited_keys = work_keys.get(cited_wid, ())
        for u in citing_keys:
            for v in cited_keys:
                if u == v:
                    continue
                key = (u, v)
                weights[key] = weights.get(key, 0) + 1
    # Full weighted digraph, exactly as before; add_edges_from is used instead
    # of per-pair add_edge calls for speed.
    graph = nx.DiGraph()
    graph.add_edges_from(((u, v, {"weight": w}) for (u, v), w in weights.items()))
    rings = []
    for component in nx.strongly_connected_components(graph):
        if not 3 <= len(component) <= 6:
            continue
        members = list(component)
        ok = all(
            graph.get_edge_data(u, v, {}).get("weight", 0) >= k
            and graph.get_edge_data(v, u, {}).get("weight", 0) >= k
            for i, u in enumerate(members) for v in members[i + 1:]
        )
        if ok:
            rings.append({"authors": sorted(members), "min_mutual": k})
    return rings


def detect_citation_rings(session, policy) -> list:
    """Global ring detection: strongly connected author groups of size 3-6 where
    every ordered pair has mutual citations >= ring_min_mutual_citations."""
    k = policy_value(policy, "ring_min_mutual_citations", 4)
    authors = {a.id: a for a in session.query(Author).all()}
    node_key = {aid: _author_node_key(a) for aid, a in authors.items()}
    authorships = {}
    for ah in session.query(Authorship.work_id, Authorship.author_id).all():
        authorships.setdefault(ah[0], []).append(ah[1])
    work_keys = {wid: [node_key[aid] for aid in aids]
                 for wid, aids in authorships.items()}
    cit_pairs = session.query(Citation.citing_work_id,
                              Citation.cited_work_id).all()
    return _rings_from_preloaded(work_keys, cit_pairs, k)


def run_integrity(session, policy) -> dict:
    """Compute and persist flags for every researcher and institution.

    All scope data is preloaded once (citations, classifications, authorships);
    per-scope flag decisions are identical to detect_integrity_flags.
    """
    from sqlalchemy import func

    session.query(IntegrityFlag).delete()
    rings = detect_citation_rings(session, policy)
    ring_members = {a for r in rings for a in r["authors"]} or None

    # Global preload (plain tuples, no ORM objects in the hot loop).
    cit_rows = session.query(Citation.id, Citation.citing_work_id,
                             Citation.cited_work_id).order_by(Citation.id).all()
    cit_info = {cid: (citing, cited) for cid, citing, cited in cit_rows}
    scope_cits: dict = {}
    for author_id, inst_id, cid in (
        session.query(Authorship.author_id, Authorship.institution_id, Citation.id)
        .join(Citation, Citation.cited_work_id == Authorship.work_id)
        .all()
    ):
        citing, cited = cit_info[cid]
        scope_cits.setdefault(("researcher", author_id), []).append((cid, citing, cited))
        if inst_id is not None:
            scope_cits.setdefault(("institution", inst_id), []).append((cid, citing, cited))
    for key in scope_cits:
        scope_cits[key].sort(key=lambda t: t[0])

    internal_counts: dict = {}
    for scope_type, scope_id, klass, n in (
        session.query(CitationClassification.scope_type,
                      CitationClassification.scope_id,
                      CitationClassification.klass,
                      func.count(CitationClassification.id))
        .filter(CitationClassification.scope_type.in_(("researcher", "institution")),
                CitationClassification.policy_id == policy.id,
                CitationClassification.policy_version == policy.version)
        .group_by(CitationClassification.scope_type,
                  CitationClassification.scope_id,
                  CitationClassification.klass)
        .all()
    ):
        internal_counts.setdefault((scope_type, scope_id), {})[klass] = n

    retracted = {wid: bool(is_r) for wid, is_r in
                 session.query(Work.id, Work.is_retracted).all()}
    work_author_keys: dict = {}
    for wid, oa_id, orcid, name_key, display_name in (
        session.query(Authorship.work_id, Author.openalex_id, Author.orcid,
                      Author.name_key, Author.display_name)
        .join(Author, Authorship.author_id == Author.id)
        .order_by(Authorship.work_id, Authorship.id)
        .all()
    ):
        work_author_keys.setdefault(wid, []).append(
            (_node_key(oa_id, orcid, name_key), display_name))

    ring_works = ({wid for wid, keys in work_author_keys.items()
                 if any(k in ring_members for k, _ in keys)}
                if ring_members else None)

    counts = {}
    for (scope_type, scope_id), citations in scope_cits.items():
        unique = len(citations)
        internal = internal_counts.get((scope_type, scope_id), {}).get("internal", 0)
        internal_ratio = round(internal / unique, 4) if unique else 0.0
        flags = _compute_flags(
            scope_type=scope_type, scope_id=scope_id, policy=policy,
            unique=unique, internal_ratio=internal_ratio, citations=citations,
            work_author_keys=work_author_keys, retracted=retracted,
            ring_members=ring_members, ring_works=ring_works)
        for f in flags:
            session.add(IntegrityFlag(
                flag_type=f["flag_type"], scope_type=f["scope_type"],
                scope_id=f["scope_id"], severity=f["severity"], details=f["details"]))
            counts[f["flag_type"]] = counts.get(f["flag_type"], 0) + 1
    session.flush()
    counts["rings_detected"] = len(rings)
    return counts
