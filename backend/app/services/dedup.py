"""Duplicate elimination cascade — PRD section 5.2.

Input contract: run_dedup(session, policy, raw_works, semantic_cache) where
each raw work is a dict with keys:
    record_id, title, doi, pmid, pmcid, year, venue, pub_type,
    is_preprint, is_retracted, mesh_terms, source, retrieved_at,
    is_synthetic, openalex_id, authors
and each author is a dict with keys:
    openalex_id, orcid, display_name, last_name, first_name, name_key,
    position (first|middle|last), institution_ror, institution_name,
    country_code, raw_affiliation

Cascade (first match wins, level-major over clusters):
  L1 exact_id: same normalized DOI / PMID / PMCID -> auto-merge, conf 1.0
  L2 title_year_author_hash: same sha256(title_norm|year|first_author) -> auto-merge, conf 0.97
  L3 fuzzy_title: same block (first-author surname, year +-1),
      rapidfuzz token_set_ratio >= policy.dedup_auto_threshold (default 92),
      year diff <= 1, >= 1 shared author surname -> auto-merge, conf = score/100
  L3b semantic_title (optional): cached embedding cosine >= 0.93 with the same
      L3 side conditions -> auto-merge, conf = score. Never overrides the
      part guard or rejected_merges.
  L4: score in [dedup_review_min (default 80), auto_threshold) -> review queue,
      never merged.
Part guard: numeric tokens, roman numerals and part/phase/trial tokens must
  match between two candidate titles, otherwise never auto-merge -> review.
  The guard applies to fuzzy levels (L3/L3b/preprint), not to exact L1/L2.
Preprint rule: one record preprint (medRxiv/bioRxiv/SSRN/arXiv) and the other a
  journal article, title score >= 95, author overlap >= 50%, year diff <= 2
  -> auto-merge as preprint_to_published, published record becomes canonical.
Rejected pairs (rejected_merges) are never merged again. Human-approved review
  pairs are unioned into clusters before the cascade runs.

Every raw record (including the canonical one) gets a work_aliases row so that
raw_record_id -> canonical work_id is a total mapping for the edges stage.
The canonical record's alias row carries merge_reason='primary'.
"""
import hashlib
import re
from collections import defaultdict
from datetime import datetime

from rapidfuzz import fuzz

from app.models import Author, Authorship, ReviewItem, Work, WorkAlias, RejectedMerge
from app.services.normalize import (
    author_key,
    normalize_doi,
    normalize_name_part,
    normalize_pmcid,
    normalize_pmid,
    normalize_title,
)
from app.services.policy import policy_value
from app.services.semantic import cache_key as semantic_cache_key

_ROMAN_RE = re.compile(r"\b[ivxlcdm]{1,6}\b")
_NUM_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
_PART_WORDS = ("part", "phase", "trial", "stage", "arm", "wave", "cohort", "study", "series", "volume", "vol", "chapter")
_PREPRINT_HINTS = ("medrxiv", "biorxiv", "ssrn", "arxiv")


def title_year_author_hash(title_norm: str, year, first_author_lastname: str) -> str:
    return hashlib.sha256(f"{title_norm}|{year or ''}|{first_author_lastname or ''}".encode("utf-8")).hexdigest()


def part_signature(title_norm: str) -> frozenset:
    """Numeric tokens, roman numerals and part/phase/trial+n tokens."""
    sig = set()
    for m in _NUM_RE.finditer(title_norm):
        sig.add(m.group())
    for m in _ROMAN_RE.finditer(title_norm):
        sig.add("roman:" + m.group())
    tokens = title_norm.split()
    for i, tok in enumerate(tokens):
        if tok in _PART_WORDS and i + 1 < len(tokens) and re.fullmatch(r"[a-z0-9]+", tokens[i + 1]):
            sig.add(f"{tok} {tokens[i + 1]}")
    return frozenset(sig)


def part_guard_triggers(title_a_norm: str, title_b_norm: str) -> bool:
    """True when the part signatures differ -> never auto-merge."""
    return part_signature(title_a_norm) != part_signature(title_b_norm)


def is_preprint_record(rec: dict) -> bool:
    if rec.get("is_preprint"):
        return True
    blob = f"{rec.get('source') or ''} {rec.get('venue') or ''}".lower()
    if any(h in blob for h in _PREPRINT_HINTS):
        return True
    return (rec.get("pub_type") or "").lower() == "preprint"


def _author_surnames(rec: dict) -> set:
    return {a["_surname_norm"] for a in rec["authors"] if a["_surname_norm"]}


def _first_author(rec: dict) -> dict | None:
    for a in rec["authors"]:
        if a.get("position") == "first":
            return a
    return rec["authors"][0] if rec["authors"] else None


def _coerce_datetime(value):
    """Accept datetime objects or ISO strings (JSON cache data)."""
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _prepare_record(raw: dict) -> dict:
    authors = []
    for i, a in enumerate(raw.get("authors") or []):
        a = dict(a)
        last = a.get("last_name") or ""
        first = a.get("first_name") or ""
        if not a.get("name_key"):
            a["name_key"] = author_key(last, first)
        a["_surname_norm"] = normalize_name_part(last)
        if i == 0 and not a.get("position"):
            a["position"] = "first"
        authors.append(a)
    title_norm = normalize_title(raw.get("title"))
    first = None
    for a in authors:
        if a.get("position") == "first":
            first = a
            break
    first = first or (authors[0] if authors else None)
    first_surname = (first or {}).get("_surname_norm", "")
    _l2_hash = (
        title_year_author_hash(title_norm, raw.get("year"), first_surname)
        if title_norm else None
    )
    return {
        "record_id": raw.get("record_id"),
        "title": raw.get("title") or "",
        "title_norm": title_norm,
        "doi": normalize_doi(raw.get("doi")),
        "pmid": normalize_pmid(raw.get("pmid")),
        "pmcid": normalize_pmcid(raw.get("pmcid")),
        "year": raw.get("year"),
        "venue": raw.get("venue"),
        "pub_type": raw.get("pub_type"),
        "is_preprint": bool(raw.get("is_preprint")),
        "is_retracted": bool(raw.get("is_retracted")),
        "mesh_terms": raw.get("mesh_terms") or [],
        "source": raw.get("source") or "",
        "retrieved_at": _coerce_datetime(raw.get("retrieved_at")),
        "is_synthetic": bool(raw.get("is_synthetic")),
        "openalex_id": raw.get("openalex_id"),
        "authors": authors,
        "first_surname": first_surname,
        "_l2_hash": _l2_hash,
        "raw": raw,
    }


def _same_identifier(a: dict, b: dict) -> bool:
    for key in ("doi", "pmid", "pmcid"):
        if a[key] and b[key] and a[key] == b[key]:
            return True
    return False


def _fuzzy_score(a: dict, b: dict) -> float:
    return fuzz.token_set_ratio(a["title_norm"], b["title_norm"])


def _year_diff_ok(a: dict, b: dict, limit: int) -> bool:
    if a["year"] is None or b["year"] is None:
        return True
    return abs(a["year"] - b["year"]) <= limit


def _author_overlap(a: dict, b: dict) -> float:
    sa, sb = _author_surnames(a), _author_surnames(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / min(len(sa), len(sb))


def _completeness(rec: dict) -> int:
    return sum(bool(rec.get(k)) for k in ("title", "year", "venue", "doi", "pmid")) + (1 if rec["authors"] else 0)


def _canonical_rank(rec: dict) -> tuple:
    """Lower is better: published > DOI > PMID > complete > earliest retrieved."""
    return (
        is_preprint_record(rec),
        not rec["doi"],
        not rec["pmid"],
        -_completeness(rec),
        str(rec.get("retrieved_at") or ""),
    )


def _choose_primary(members: list) -> dict:
    return min(members, key=_canonical_rank)


def _record_summary(rec: dict) -> dict:
    return {
        "record_id": rec["record_id"],
        "title": rec["title"],
        "doi": rec["doi"],
        "year": rec["year"],
        "authors": [a.get("display_name") for a in rec["authors"]],
        "is_preprint": rec["is_preprint"],
    }


def _ordered_pair(a: str, b: str) -> tuple:
    return (a, b) if a <= b else (b, a)


def _load_rejected(session) -> set:
    return {(r.raw_record_a, r.raw_record_b) for r in session.query(RejectedMerge).all()}


def _load_approved_pairs(session) -> list:
    pairs = []
    for item in session.query(ReviewItem).filter_by(item_type="dedup", status="approved").all():
        p = item.payload or {}
        if p.get("record_a_id") and p.get("record_b_id"):
            pairs.append(_ordered_pair(p["record_a_id"], p["record_b_id"]))
    return pairs


def apply_manual_merge(session, record_a_id: str, record_b_id: str) -> dict:
    """Merge two canonical works after a human approved a dedup review item.

    Remaps citations (merging on UNIQUE conflicts), moves aliases, deletes the
    loser work. Classifications/evidence for touched citations are dropped so
    the pipeline stages recompute them.
    """
    from app.models import Citation, CitationClassification, Evidence, Mention

    wa = session.query(WorkAlias).filter_by(raw_record_id=record_a_id).first()
    wb = session.query(WorkAlias).filter_by(raw_record_id=record_b_id).first()
    if not wa or not wb:
        return {"merged": False, "reason": "record_not_found"}
    if wa.work_id == wb.work_id:
        return {"merged": False, "reason": "already_same_work"}
    work_a = session.get(Work, wa.work_id)
    work_b = session.get(Work, wb.work_id)

    def work_rank(w: Work) -> tuple:
        return (w.is_preprint, not w.doi, not w.pmid, w.id)

    winner, loser = (work_a, work_b) if work_rank(work_a) <= work_rank(work_b) else (work_b, work_a)

    touched_citations = set()
    for cit in session.query(Citation).filter(
        (Citation.citing_work_id == loser.id) | (Citation.cited_work_id == loser.id)
    ).all():
        new_pair = (
            winner.id if cit.citing_work_id == loser.id else cit.citing_work_id,
            winner.id if cit.cited_work_id == loser.id else cit.cited_work_id,
        )
        touched_citations.add(cit.id)
        if new_pair[0] == new_pair[1]:
            session.delete(cit)  # self-citation artifact of the merge
            continue
        existing = session.query(Citation).filter_by(
            citing_work_id=new_pair[0], cited_work_id=new_pair[1]
        ).first()
        if existing and existing.id != cit.id:
            for m in cit.mentions:
                m.citation_id = existing.id
            existing.mention_count += cit.mention_count
            existing.raw_rows_total += cit.raw_rows_total
            existing.duplicates_removed += cit.duplicates_removed
            existing.repeats_removed += cit.repeats_removed
            touched_citations.add(existing.id)
            session.delete(cit)
        else:
            cit.citing_work_id, cit.cited_work_id = new_pair
            touched_citations.add(cit.id)

    for alias in session.query(WorkAlias).filter_by(work_id=loser.id).all():
        alias.work_id = winner.id
        if alias.merge_reason == "primary":
            alias.merge_reason = "manual"
            alias.merge_confidence = 1.0
            alias.status = "approved"
    for ah in session.query(Authorship).filter_by(work_id=loser.id).all():
        dup = session.query(Authorship).filter_by(work_id=winner.id, author_id=ah.author_id).first()
        if dup:
            session.delete(ah)
        else:
            ah.work_id = winner.id
    session.delete(loser)

    if touched_citations:
        session.query(CitationClassification).filter(
            CitationClassification.citation_id.in_(touched_citations)
        ).delete(synchronize_session=False)
        session.query(Evidence).filter(Evidence.citation_id.in_(touched_citations)).delete(
            synchronize_session=False
        )
    session.flush()
    return {"merged": True, "winner_work_id": winner.id, "loser_work_id": loser.id}


def run_dedup(session, policy, raw_works: list | None = None, semantic_cache: dict | None = None) -> dict:
    """Run the dedup cascade. Returns counts by merge reason plus queued items."""
    from app.services import review as review_svc  # local import: review imports dedup

    raw_works = raw_works or []
    auto_threshold = policy_value(policy, "dedup_auto_threshold", 92)
    review_min = policy_value(policy, "dedup_review_min", 80)
    semantic_threshold = 0.93

    prepared = [_prepare_record(r) for r in raw_works]
    by_id = {p["record_id"]: p for p in prepared}
    rejected = _load_rejected(session)

    # Seed clusters from human-approved dedup decisions (union-find).
    parent = {p["record_id"]: p["record_id"] for p in prepared}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for a_id, b_id in _load_approved_pairs(session):
        if a_id in by_id and b_id in by_id and _ordered_pair(a_id, b_id) not in rejected:
            union(a_id, b_id)

    # clusters: list of {"members": [...]}. Only human-approved pairs seed
    # clusters; every other record enters through the cascade below.
    seed_groups = defaultdict(list)
    for p in prepared:
        seed_groups[find(p["record_id"])].append(p)
    clusters = []
    merge_info = {}  # record_id -> (reason, confidence, fuzzy_score, status)
    counts = defaultdict(int)
    for members in seed_groups.values():
        if len(members) < 2:
            continue
        primary = _choose_primary(members)
        for m in members:
            if m["record_id"] != primary["record_id"]:
                merge_info[m["record_id"]] = ("manual", 1.0, None, "approved")
                counts["manual"] += 1
        merge_info[primary["record_id"]] = ("primary", 1.0, None, "auto")
        cluster = {"members": members, "primary": primary, "merge_reason": "manual"}
        clusters.append(cluster)
    clusters.sort(key=lambda c: c["primary"]["record_id"])

    # Identifier + L2 hash indexes over cluster primaries. A merge can change a
    # cluster's primary, so entries are refreshed on every try_merge; lookups
    # below stay equivalent to the original first-match-in-list-order scan.
    _cluster_order = {id(c): i for i, c in enumerate(clusters)}
    l2_index: dict = {}   # l2 hash -> cluster
    id_index: dict = {}   # (kind, normalized value) -> cluster

    def _index_cluster(c):
        pr = c["primary"]
        if pr["_l2_hash"]:
            l2_index[pr["_l2_hash"]] = c
        for kind in ("doi", "pmid", "pmcid"):
            if pr[kind]:
                id_index[(kind, pr[kind])] = c
        c["_indexed"] = True

    def _unindex_cluster(c):
        if not c.get("_indexed"):
            return
        pr = c["primary"]
        if pr["_l2_hash"] and l2_index.get(pr["_l2_hash"]) is c:
            del l2_index[pr["_l2_hash"]]
        for kind in ("doi", "pmid", "pmcid"):
            if pr[kind] and id_index.get((kind, pr[kind])) is c:
                del id_index[(kind, pr[kind])]
        c["_indexed"] = False

    for c in clusters:
        _index_cluster(c)

    placed = {m["record_id"] for c in clusters for m in c["members"]}

    review_candidates = []  # (pair, rule, score)

    def _first_in_order(cands):
        seen = set()
        uniq = []
        for c in cands:
            if id(c) not in seen:
                seen.add(id(c))
                uniq.append(c)
        return min(uniq, key=lambda c: _cluster_order[id(c)])

    def try_merge(rec, cluster, reason, confidence, fuzzy_score=None):
        if _ordered_pair(rec["record_id"], cluster["primary"]["record_id"]) in rejected:
            return False
        _unindex_cluster(cluster)
        cluster["members"].append(rec)
        cluster["primary"] = _choose_primary(cluster["members"])
        cluster["merge_reason"] = reason
        _index_cluster(cluster)
        merge_info[rec["record_id"]] = (reason, confidence, fuzzy_score, "auto")
        counts[reason] += 1
        placed.add(rec["record_id"])
        return True

    for rec in sorted(prepared, key=lambda p: p["record_id"] or ""):
        if rec["record_id"] in placed:
            continue
        merged = False
        pending_reviews = []
        # L1: exact identifier (index lookup; first-in-list-order on ties)
        if not merged:
            cands = []
            for kind in ("doi", "pmid", "pmcid"):
                if rec[kind] and (kind, rec[kind]) in id_index:
                    cands.append(id_index[(kind, rec[kind])])
            if cands:
                merged = try_merge(rec, _first_in_order(cands), "exact_id", 1.0)
        # L2: title/year/author hash (needs a real title)
        if not merged and rec["_l2_hash"] and rec["_l2_hash"] in l2_index:
            merged = try_merge(rec, l2_index[rec["_l2_hash"]], "title_year_author_hash", 0.97)
        # Preprint rule + L3 fuzzy + L3b semantic, all within blocks
        if not merged and rec["title_norm"]:
            for c in clusters:
                pr = c["primary"]
                if not pr["title_norm"]:
                    continue
                if rec["first_surname"] != pr["first_surname"]:
                    continue  # blocking: same first-author surname
                pair = _ordered_pair(rec["record_id"], pr["record_id"])
                if pair in rejected:
                    continue
                pre_a, pre_b = is_preprint_record(rec), is_preprint_record(pr)
                year_limit = 2 if (pre_a != pre_b) else 1
                if not _year_diff_ok(rec, pr, year_limit):
                    continue
                score = _fuzzy_score(rec, pr)
                shared = bool(_author_surnames(rec) & _author_surnames(pr))
                guard = part_guard_triggers(rec["title_norm"], pr["title_norm"])
                # Preprint rule
                if pre_a != pre_b and score >= 95 and _author_overlap(rec, pr) >= 0.5:
                    if guard:
                        pending_reviews.append((pair, "part_guard", score))
                    else:
                        merged = try_merge(rec, c, "preprint_to_published", score / 100, score)
                        break
                    continue
                if not shared:
                    continue
                sem = None
                if semantic_cache:
                    sem = semantic_cache.get(semantic_cache_key(rec["title_norm"], pr["title_norm"]))
                if guard:
                    if score >= review_min or (sem is not None and sem >= semantic_threshold):
                        pending_reviews.append((pair, "part_guard", score))
                    continue
                if score >= auto_threshold:
                    merged = try_merge(rec, c, "fuzzy_title", round(score / 100, 3), score)
                    break
                if sem is not None and sem >= semantic_threshold:
                    merged = try_merge(rec, c, "semantic_title", round(sem, 3), score)
                    break
                if score >= review_min or (pre_a != pre_b and score >= review_min):
                    rule = "preprint_candidate" if (pre_a != pre_b) else "fuzzy_review"
                    pending_reviews.append((pair, rule, score))
        if not merged:
            primary = rec
            merge_info.setdefault(rec["record_id"], ("primary", 1.0, None, "auto"))
            new_cluster = {"members": [rec], "primary": primary}
            _cluster_order[id(new_cluster)] = len(_cluster_order)
            clusters.append(new_cluster)
            _index_cluster(new_cluster)
            placed.add(rec["record_id"])
        for pair, rule, score in pending_reviews:
            review_candidates.append((pair, rule, score, rec, by_id[pair[0]], by_id[pair[1]]))

    # Write review items (dedupe by pair).
    seen_pairs = set()
    queued = 0
    for pair, rule, score, _rec, pa, pb in review_candidates:
        if pair in seen_pairs or pair in rejected:
            continue
        seen_pairs.add(pair)
        review_svc.create_review_item(
            session,
            "dedup",
            {
                "record_a_id": pair[0],
                "record_b_id": pair[1],
                "record_a": _record_summary(pa),
                "record_b": _record_summary(pb),
                "rule": rule,
                "reasons": [f"similarity={score:.1f}", f"rule={rule}"],
            },
            score=round(score, 2),
        )
        queued += 1

    # Normalize merge_info: exactly one alias per cluster carries
    # merge_reason='primary' — the record the canonical Work is built from.
    # A displaced seed primary takes the cluster's merge reason.
    for cluster in clusters:
        primary_id = cluster["primary"]["record_id"]
        for m in cluster["members"]:
            rid = m["record_id"]
            info = merge_info.get(rid)
            if rid == primary_id:
                status = info[3] if info and info[3] == "approved" else "auto"
                merge_info[rid] = ("primary", 1.0, None, status)
            elif not info or info[0] == "primary":
                merge_info[rid] = (
                    cluster.get("merge_reason") or "manual",
                    1.0,
                    info[2] if info else None,
                    info[3] if info else "auto",
                )

    # Persist: rebuild works / aliases / authors / authorships.
    session.query(Authorship).delete()
    session.query(WorkAlias).delete()
    session.query(Work).delete()
    # Drop authors no longer referenced.
    session.query(Author).delete()

    author_map = {}  # (openalex_id|orcid|name_key) -> Author

    def get_author(a: dict) -> Author:
        # No flush here: new authors are flushed once per cluster below, in the
        # same insertion order as before, so autoincrement ids are unchanged.
        for k in (a.get("openalex_id"), a.get("orcid"), a.get("name_key")):
            if k and k in author_map:
                return author_map[k]
        author = Author(
            openalex_id=a.get("openalex_id"),
            orcid=a.get("orcid"),
            display_name=a.get("display_name") or a.get("name_key") or "Unknown",
            name_key=a.get("name_key"),
        )
        session.add(author)
        for k in (a.get("openalex_id"), a.get("orcid"), a.get("name_key")):
            if k:
                author_map[k] = author
        return author

    # Single flush at the end: FKs resolve via relationships, so per-cluster
    # flushes are unnecessary. ID assignment order changes vs the old code, but
    # IDs are opaque keys — all queries are by attributes.
    # Collect alias/authorship rows for Core bulk insert (avoids 19k ORM
    # objects). Works and authors stay ORM for ID generation and dedup.
    alias_rows = []
    authorship_rows = []
    for cluster in sorted(clusters, key=lambda c: c["primary"]["record_id"] or ""):
        primary = cluster["primary"]
        work = Work(
            openalex_id=primary.get("openalex_id"),
            doi=primary["doi"],
            pmid=primary["pmid"],
            pmcid=primary["pmcid"],
            title=primary["title"],
            title_norm=primary["title_norm"],
            year=primary["year"],
            venue=primary["venue"],
            pub_type=primary["pub_type"],
            is_preprint=is_preprint_record(primary),
            is_retracted=primary["is_retracted"],
            mesh_terms=primary["mesh_terms"],
            source=primary["source"],
            retrieved_at=primary.get("retrieved_at"),
            is_synthetic=any(m["is_synthetic"] for m in cluster["members"]),
        )
        session.add(work)
        for m in cluster["members"]:
            reason, conf, fscore, status = merge_info.get(
                m["record_id"], ("primary", 1.0, None, "auto")
            )
            alias_rows.append((work, m, reason, conf, fscore, status))
        seen_authors = set()
        for a in primary["authors"]:
            author = get_author(a)
            if id(author) in seen_authors:
                continue
            seen_authors.add(id(author))
            authorship_rows.append(
                (work, author, a.get("position"), a.get("raw_affiliation")))
    session.flush()  # assigns work.id and author.id
    from sqlalchemy import insert
    if alias_rows:
        session.execute(insert(WorkAlias), [
            {"work_id": w.id, "raw_record_id": m["record_id"],
             "raw_title": m["title"], "raw_doi": m["doi"],
             "source": m["source"], "merge_reason": reason,
             "merge_confidence": conf, "fuzzy_score": fscore,
             "status": status, "is_synthetic": m["is_synthetic"]}
            for w, m, reason, conf, fscore, status in alias_rows
        ])
    if authorship_rows:
        session.execute(insert(Authorship), [
            {"work_id": w.id, "author_id": a.id, "institution_id": None,
             "position": pos, "raw_affiliation": raw_aff}
            for w, a, pos, raw_aff in authorship_rows
        ])

    result = dict(counts)
    result["queued"] = queued
    result["works"] = session.query(Work).count()
    result["aliases"] = session.query(WorkAlias).count()
    return result


def resolve_institutions(session, raw_works: list | None = None, ror_aliases: dict | None = None) -> dict:
    """PRD 11.4: create Institution rows from ROR ids seen in raw works and link
    authorships. Raw affiliation strings without a ROR become affiliation review
    items. ror_aliases maps lowercase name fragments -> ror_id for the demo."""
    from app.models import Institution
    from app.services import review as review_svc

    raw_works = raw_works or []
    ror_aliases = ror_aliases or {}
    created, linked, affiliation_queued = 0, 0, 0

    ror_info = {}
    for rw in raw_works:
        for a in rw.get("authors") or []:
            ror = a.get("institution_ror")
            if ror:
                ror_info.setdefault(ror, {"name": a.get("institution_name") or ror,
                                         "country": a.get("country_code")})
            elif a.get("raw_affiliation"):
                frag = (a.get("raw_affiliation") or "").lower()
                for needle, mapped_ror in ror_aliases.items():
                    if needle in frag:
                        ror_info.setdefault(mapped_ror, {"name": a.get("raw_affiliation"), "country": None})
                        a["institution_ror"] = mapped_ror
                        break

    # Bulk institution upsert: one query for existing, one flush for new.
    existing = {i.ror_id: i for i in session.query(Institution).filter(
        Institution.ror_id.in_(list(ror_info.keys()) or [""])).all()}
    ror_to_inst = {}
    for ror, info in ror_info.items():
        inst = existing.get(ror)
        if inst is None:
            inst = Institution(ror_id=ror, name=info["name"], country_code=info["country"])
            session.add(inst)
            created += 1
        ror_to_inst[ror] = inst
    if created:
        session.flush()

    # Link authorships via (canonical work, author) matching.
    alias_rows = session.query(WorkAlias).all()
    rec2work = {al.raw_record_id: al.work_id for al in alias_rows}
    author_rows = session.query(Author).all()
    by_id_key = {}
    for au in author_rows:
        for k in (au.openalex_id, au.orcid, au.name_key):
            if k:
                by_id_key.setdefault(k, au)

    # Preload all authorships once: the per-author query below was the hotspot.
    authorship_map = {(ah.work_id, ah.author_id): ah
                      for ah in session.query(Authorship).all()}
    seen_affiliations = set()
    for rw in raw_works:
        work_id = rec2work.get(rw.get("record_id"))
        if not work_id:
            continue
        for a in rw.get("authors") or []:
            author = None
    # name_key may be missing on raw dicts (_prepare_record fills it on a copy)
            fallback_key = author_key(a.get("last_name") or "", a.get("first_name") or "")
            for k in (a.get("openalex_id"), a.get("orcid"), a.get("name_key") or fallback_key):
                if k and k in by_id_key:
                    author = by_id_key[k]
                    break

            if not author:
                continue
            ah = authorship_map.get((work_id, author.id))
            ror = a.get("institution_ror")
            if ror and ror in ror_to_inst:
                if not ah:
                    ah = Authorship(work_id=work_id, author_id=author.id,
                                    position=a.get("position"),
                                    raw_affiliation=a.get("raw_affiliation"))
                    session.add(ah)
                    authorship_map[(work_id, author.id)] = ah
                if ah.institution_id != ror_to_inst[ror].id:
                    ah.institution_id = ror_to_inst[ror].id
                    linked += 1
            elif a.get("raw_affiliation") and a["raw_affiliation"] not in seen_affiliations:
                seen_affiliations.add(a["raw_affiliation"])
                review_svc.create_review_item(
                    session, "affiliation",
                    {"affiliation": a["raw_affiliation"],
                     "author": a.get("display_name"),
                     "record_id": rw.get("record_id")},
                )
                affiliation_queued += 1
    session.flush()
    return {"institutions_created": created, "authorships_linked": linked,
            "affiliation_review_queued": affiliation_queued}
