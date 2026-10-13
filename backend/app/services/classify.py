"""Citation classification — PRD section 5.5. Pure function, no I/O.

classify(citing, cited, scope, policy) -> ('self' | 'internal' | 'external', reason_dict)

Author identity prefers OpenAlex author ID, then ORCID, then name_key
(lastname + first initial). Name-key matches are flagged in the reason.
Affiliations are compared as ROR ids. policy may be a config dict or an object
with attributes (policy_value handles both).
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AuthorView:
    openalex_id: str | None = None
    orcid: str | None = None
    name_key: str = ""
    position: str | None = None  # first | middle | last
    ror_ids: tuple = ()


@dataclass(frozen=True)
class WorkView:
    authors: tuple = ()


@dataclass(frozen=True)
class ResearcherScope:
    researcher_openalex_id: str | None = None
    researcher_orcid: str | None = None
    researcher_name_key: str = ""
    researcher_rors: tuple = ()  # RORs the researcher had on the cited paper


@dataclass(frozen=True)
class InstitutionScope:
    ror_id: str = ""


@dataclass(frozen=True)
class PaperScope:
    pass


def _policy(policy, key, default=None):
    # Bug fix (PRD T9): Policy ORM objects carry settings in .config; the old
    # getattr fallback silently ignored them, so policy changes never took
    # effect. Dict policies and plain attributes still work as before.
    if isinstance(policy, dict):
        return policy.get(key, default)
    config = getattr(policy, "config", None)
    if isinstance(config, dict) and key in config:
        return config[key]
    return getattr(policy, key, default)


def _considered(authors: tuple, policy) -> tuple:
    if _policy(policy, "citing_authors_considered", "any") == "first_last":
        return tuple(a for a in authors if a.position in ("first", "last"))
    return authors


def _match_strength(a: AuthorView, b: AuthorView) -> str | None:
    """'id' for OpenAlex/ORCID match, 'name' for name_key fallback, else None."""
    if a.openalex_id and b.openalex_id and a.openalex_id == b.openalex_id:
        return "id"
    if a.orcid and b.orcid and a.orcid == b.orcid:
        return "id"
    if a.name_key and b.name_key and a.name_key == b.name_key:
        return "name"
    return None


def _researcher_view(scope: ResearcherScope) -> AuthorView:
    return AuthorView(
        openalex_id=scope.researcher_openalex_id,
        orcid=scope.researcher_orcid,
        name_key=scope.researcher_name_key,
    )


def _policy_stamp(policy) -> dict:
    if isinstance(policy, dict):
        return {}
    return {"policy_id": getattr(policy, "id", None), "policy_version": getattr(policy, "version", None)}


def classify(citing: WorkView, cited: WorkView, scope, policy) -> tuple:
    """Returns (klass, reason_dict). Deterministic, no I/O."""
    stamp = _policy_stamp(policy)
    considered = _considered(citing.authors, policy)

    if isinstance(scope, ResearcherScope):
        researcher = _researcher_view(scope)
        if _policy(policy, "self_citation_scope", "author") == "any_shared_author":
            for ca in considered:
                for pa in cited.authors:
                    if _match_strength(ca, pa):
                        return "self", {"rule": "self_citation_shared_author",
                                        "matched_author": ca.name_key, **stamp}
        else:
            for ca in considered:
                strength = _match_strength(ca, researcher)
                if strength:
                    reason = {"rule": "self_citation_author_match",
                              "matched_author": ca.name_key,
                              "match_by": "openalex_orcid" if strength == "id" else "name_key",
                              **stamp}
                    if strength == "name":
                        reason["note"] = "name_match_fallback"
                    return "self", reason
        researcher_rors = set(scope.researcher_rors or ())
        for ca in considered:
            shared = set(ca.ror_ids or ()) & researcher_rors
            if shared:
                return "internal", {"rule": "internal_shared_institution",
                                    "matched_ror": sorted(shared)[0],
                                    "citing_author": ca.name_key, **stamp}
        reason = {"rule": "no_shared_author_or_institution", **stamp}
        if any(not ca.ror_ids for ca in considered):
            reason["note"] = "unresolved_affiliation"
        return "external", reason

    if isinstance(scope, InstitutionScope):
        for ca in citing.authors:
            for pa in cited.authors:
                if _match_strength(ca, pa):
                    return "self", {"rule": "self_citation_shared_author",
                                    "matched_author": ca.name_key, **stamp}
        for ca in considered:
            if scope.ror_id and scope.ror_id in set(ca.ror_ids or ()):
                return "internal", {"rule": "internal_shared_institution",
                                    "matched_ror": scope.ror_id,
                                    "citing_author": ca.name_key, **stamp}
        reason = {"rule": "no_shared_author_or_institution", **stamp}
        if any(not ca.ror_ids for ca in considered):
            reason["note"] = "unresolved_affiliation"
        return "external", reason

    if isinstance(scope, PaperScope):
        for ca in citing.authors:
            for pa in cited.authors:
                if _match_strength(ca, pa):
                    return "self", {"rule": "self_citation_shared_author",
                                    "matched_author": ca.name_key, **stamp}
        citing_rors = {r for ca in citing.authors for r in (ca.ror_ids or ())}
        cited_rors = {r for pa in cited.authors for r in (pa.ror_ids or ())}
        if citing_rors & cited_rors:
            return "internal", {"rule": "internal_shared_institution",
                                "matched_ror": sorted(citing_rors & cited_rors)[0], **stamp}
        return "external", {"rule": "no_shared_author_or_institution", **stamp}

    raise ValueError(f"unknown scope type: {type(scope).__name__}")


def build_work_view(session, work_id: int) -> WorkView:
    """Build a WorkView from authorships (institution RORs included)."""
    from app.models import Authorship, Author, Institution

    authors = []
    rows = (
        session.query(Authorship, Author, Institution)
        .join(Author, Authorship.author_id == Author.id)
        .outerjoin(Institution, Authorship.institution_id == Institution.id)
        .filter(Authorship.work_id == work_id)
        .order_by(Authorship.id)
        .all()
    )
    for ah, au, inst in rows:
        rors = (inst.ror_id,) if inst and inst.ror_id else ()
        authors.append(AuthorView(
            openalex_id=au.openalex_id,
            orcid=au.orcid,
            name_key=au.name_key or "",
            position=ah.position,
            ror_ids=rors,
        ))
    return WorkView(authors=tuple(authors))


def _researcher_rors_on_work(session, author_id: int, work_id: int) -> tuple:
    from app.models import Authorship, Institution

    rors = (
        session.query(Institution.ror_id)
        .join(Authorship, Authorship.institution_id == Institution.id)
        .filter(Authorship.work_id == work_id, Authorship.author_id == author_id,
                Institution.ror_id.isnot(None))
        .all()
    )
    return tuple(r[0] for r in rors)


def _preload_work_authors(session) -> dict:
    """All (work_id -> [(authorship_id, author, institution)]) in one query.

    Replaces the per-citation queries in the loop below; the views and scopes
    built from it are identical to the originals.
    """
    from app.models import Authorship, Author, Institution

    rows = (
        session.query(Authorship, Author, Institution)
        .join(Author, Authorship.author_id == Author.id)
        .outerjoin(Institution, Authorship.institution_id == Institution.id)
        .order_by(Authorship.work_id, Authorship.id)
        .all()
    )
    grouped: dict = {}
    for ah, au, inst in rows:
        grouped.setdefault(ah.work_id, []).append((ah, au, inst))
    return grouped


def _preload_citation_authors(session) -> dict:
    """work_id -> list of plain author tuples, ordered by authorship id.

    Each tuple: (author_id, name_key, openalex_id, orcid, position,
    institution_id, institution_ror). Plain tuples avoid ORM attribute overhead
    in the hot loop; content matches what the views/scopes carried before.
    """
    from app.models import Authorship, Author, Institution

    rows = (
        session.query(Authorship.work_id, Authorship.author_id, Author.name_key,
                      Author.openalex_id, Author.orcid, Authorship.position,
                      Authorship.institution_id, Institution.ror_id)
        .join(Author, Authorship.author_id == Author.id)
        .outerjoin(Institution, Authorship.institution_id == Institution.id)
        .order_by(Authorship.work_id, Authorship.id)
        .all()
    )
    grouped: dict = {}
    for r in rows:
        grouped.setdefault(r[0], []).append(r[1:])
    return grouped


def classify_all(session, policy) -> dict:
    """Classify every citation for researcher, institution and paper scopes.

    Researcher scope: every author of the cited work. Institution scope: every
    ROR on the cited work. Replaces rows for this policy id + version.

    Performance: per-citation matching work (identity maps, pairwise
    self-match, ror indexes) is hoisted out of the per-scope loop, so each
    scope is O(1)-ish. Every (klass, reason) decision is identical to calling
    the pure classify() per scope; rows are bulk-inserted.
    """
    from app.models import Citation, CitationClassification

    session.query(CitationClassification).filter_by(
        policy_id=policy.id, policy_version=policy.version).delete()
    counts = {"self": 0, "internal": 0, "external": 0, "rows": 0}

    stamp = _policy_stamp(policy)
    first_last_only = _policy(policy, "citing_authors_considered", "any") == "first_last"
    shared_author_mode = _policy(policy, "self_citation_scope", "author") == "any_shared_author"

    work_authors = _preload_citation_authors(session)

    def _tuples(work_id):
        # (name_key, openalex_id, orcid, rors_tuple, position)
        return [((r[1] or ""), r[2], r[3],
                 ((r[6],) if r[6] else ()), r[4])
                for r in work_authors.get(work_id, [])]

    batch = []
    citations = session.query(Citation.id, Citation.citing_work_id,
                              Citation.cited_work_id).order_by(Citation.id).all()
    for cit_id, citing_wid, cited_wid in citations:
        citing = _tuples(citing_wid)
        cited = _tuples(cited_wid)
        if first_last_only:
            considered_idx = [i for i, a in enumerate(citing) if a[4] in ("first", "last")]
        else:
            considered_idx = list(range(len(citing)))
        considered = [citing[i] for i in considered_idx]

        # Identity maps over CONSIDERED citing authors (first index wins, per key
        # type — mirrors _match_strength's per-author, id-before-name order).
        oa_map, orcid_map, name_map = {}, {}, {}
        ror_first = {}
        for pos, i in enumerate(considered_idx):
            _name, oa, orcid, rors, _posn = citing[i]
            if oa and oa not in oa_map:
                oa_map[oa] = pos
            if orcid and orcid not in orcid_map:
                orcid_map[orcid] = pos
            if _name and _name not in name_map:
                name_map[_name] = pos
            for r in rors:
                if r not in ror_first:
                    ror_first[r] = pos
        considered_has_unresolved = any(not a[3] for a in considered)

        # Hoisted pairwise self-match over ALL citing x cited authors (the exact
        # loop the institution/paper scopes ran per scope).
        cited_key_oa = {a[1] for a in cited if a[1]}
        cited_key_orcid = {a[2] for a in cited if a[2]}
        cited_key_name = {a[0] for a in cited if a[0]}
        pairwise_self_name = None
        for ca in citing:
            _cn, coa, corcid, _cr, _cp = ca
            hit = ((coa and coa in cited_key_oa)
                   or (corcid and corcid in cited_key_orcid)
                   or (_cn and _cn in cited_key_name))
            if hit:
                pairwise_self_name = _cn
                break
        # Hoisted any_shared_author check (researcher-independent).
        shared_author_name = None
        if shared_author_mode:
            for pos, a in enumerate(considered):
                _cn, coa, corcid, _cr, _cp = a
                if ((coa and coa in cited_key_oa)
                        or (corcid and corcid in cited_key_orcid)
                        or (_cn and _cn in cited_key_name)):
                    shared_author_name = _cn
                    break

        citing_ror_set = {r for a in citing for r in a[3]}
        cited_ror_set = {r for a in cited for r in a[3]}

        # Researcher scopes: one per cited-work author (rors grouped per author).
        cited_rows = work_authors.get(cited_wid, [])
        author_rors: dict = {}
        author_info: dict = {}
        for r in cited_rows:
            aid, name_key, oa, orcid = r[0], r[1] or "", r[2], r[3]
            if r[6]:
                author_rors.setdefault(aid, set()).add(r[6])
            if aid not in author_info:
                author_info[aid] = (name_key, oa, orcid)
        for aid, (r_name, r_oa, r_orcid) in author_info.items():
            r_rors = author_rors.get(aid, set())
            if shared_author_mode and shared_author_name is not None:
                klass, reason = "self", {"rule": "self_citation_shared_author",
                                         "matched_author": shared_author_name, **stamp}
            else:
                cands = []
                if r_oa and r_oa in oa_map:
                    cands.append((oa_map[r_oa], 0))
                if r_orcid and r_orcid in orcid_map:
                    cands.append((orcid_map[r_orcid], 0))
                if r_name and r_name in name_map:
                    cands.append((name_map[r_name], 1))
                klass = reason = None
                if cands:
                    win_pos, prio = min(cands)
                    ca = considered[win_pos]
                    strength = "id" if prio == 0 else "name"
                    reason = {"rule": "self_citation_author_match",
                              "matched_author": ca[0],
                              "match_by": "openalex_orcid" if strength == "id" else "name_key",
                              **stamp}
                    if strength == "name":
                        reason["note"] = "name_match_fallback"
                    klass = "self"
                else:
                    win = None
                    for r in r_rors:
                        idx = ror_first.get(r)
                        if idx is not None and (win is None or idx < win):
                            win = idx
                    if win is not None:
                        ca = considered[win]
                        shared = set(ca[3]) & r_rors
                        klass = "internal"
                        reason = {"rule": "internal_shared_institution",
                                  "matched_ror": sorted(shared)[0],
                                  "citing_author": ca[0], **stamp}
                    else:
                        klass = "external"
                        reason = {"rule": "no_shared_author_or_institution", **stamp}
                        if considered_has_unresolved:
                            reason["note"] = "unresolved_affiliation"
            batch.append({"citation_id": cit_id, "scope_type": "researcher",
                          "scope_id": aid, "policy_id": policy.id,
                          "policy_version": policy.version,
                          "klass": klass, "reason": reason})
            counts[klass] += 1
            counts["rows"] += 1

        # Institution scopes: distinct RORs on the cited work.
        seen_inst = set()
        for r in cited_rows:
            inst_id, inst_ror = r[5], r[6]
            if not inst_ror or inst_id in seen_inst:
                continue
            seen_inst.add(inst_id)
            if pairwise_self_name is not None:
                klass, reason = "self", {"rule": "self_citation_shared_author",
                                         "matched_author": pairwise_self_name, **stamp}
            else:
                win = ror_first.get(inst_ror)
                if win is not None:
                    klass = "internal"
                    reason = {"rule": "internal_shared_institution",
                              "matched_ror": inst_ror,
                              "citing_author": considered[win][0], **stamp}
                else:
                    klass = "external"
                    reason = {"rule": "no_shared_author_or_institution", **stamp}
                    if considered_has_unresolved:
                        reason["note"] = "unresolved_affiliation"
            batch.append({"citation_id": cit_id, "scope_type": "institution",
                          "scope_id": inst_id, "policy_id": policy.id,
                          "policy_version": policy.version,
                          "klass": klass, "reason": reason})
            counts[klass] += 1
            counts["rows"] += 1

        # Paper scope.
        if pairwise_self_name is not None:
            klass, reason = "self", {"rule": "self_citation_shared_author",
                                     "matched_author": pairwise_self_name, **stamp}
        elif citing_ror_set & cited_ror_set:
            klass = "internal"
            reason = {"rule": "internal_shared_institution",
                      "matched_ror": sorted(citing_ror_set & cited_ror_set)[0], **stamp}
        else:
            klass, reason = "external", {"rule": "no_shared_author_or_institution", **stamp}
        batch.append({"citation_id": cit_id, "scope_type": "paper",
                      "scope_id": cited_wid, "policy_id": policy.id,
                      "policy_version": policy.version,
                      "klass": klass, "reason": reason})
        counts[klass] += 1
        counts["rows"] += 1

    if batch:
        session.bulk_insert_mappings(CitationClassification, batch)
    return counts
