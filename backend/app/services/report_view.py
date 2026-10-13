"""Read-side report builders for the API (PRD 12 / 12.1).

Every number is computed from the DB via the services — never hardcoded.
"""
from app.models import Author, Authorship, Institution
from app.services.integrity import detect_integrity_flags
from app.services.metrics import (
    citation_timeline,
    institution_kpis,
    researcher_kpis,
    top_citing_institutions,
)
from app.services.policy import get_active_policy, policy_value
from app.services.waterfall import build_waterfall


def _policy(session, policy_id: int | None):
    from app.services.policy import get_policy

    if policy_id is not None:
        policy = get_policy(session, policy_id)
        if policy is None:
            raise KeyError(f"policy {policy_id} not found")
        return policy
    policy = get_active_policy(session)
    if policy is None:
        raise KeyError("no active policy; run the pipeline first")
    return policy


def _synthetic_rows(session) -> int:
    from app.models import Citation, Mention

    return (
        session.query(Citation)
        .join(Mention, Mention.citation_id == Citation.id)
        .filter(Mention.is_synthetic.is_(True))
        .count()
    )


def _waterfall_sums(session, scope_type: str, scope_id: int):
    from app.services.metrics import scope_citations

    citations = scope_citations(session, scope_type, scope_id)
    return (
        sum(c.duplicates_removed or 0 for c in citations),
        sum(c.repeats_removed or 0 for c in citations),
    )


def researcher_report(session, researcher_id: int, policy_id: int | None = None) -> dict:
    researcher = session.get(Author, researcher_id)
    if researcher is None:
        raise KeyError(f"researcher {researcher_id} not found")
    policy = _policy(session, policy_id)
    kpis = researcher_kpis(session, researcher_id, policy)
    dup, rep = _waterfall_sums(session, "researcher", researcher_id)
    headline = policy_value(policy, "headline_metric", "external_only")
    waterfall = build_waterfall(
        raw_rows=kpis["raw_rows"], duplicates_removed=dup, repeats_removed=rep,
        unique_citations=kpis["unique_citations"], self_citations=kpis["self"],
        internal_citations=kpis["internal"], external_citations=kpis["external"],
        headline_metric=headline,
    )
    rors = sorted({
        inst.ror_id for ah, inst in (
            session.query(Authorship, Institution)
            .join(Institution, Authorship.institution_id == Institution.id)
            .filter(Authorship.author_id == researcher_id, Institution.ror_id.isnot(None))
            .all()
        ) if inst.ror_id
    })
    synth = _synthetic_rows(session)
    return {
        "researcher": {"id": researcher.id, "name": researcher.display_name,
                       "orcid": researcher.orcid, "institutions": rors},
        "policy": {"id": policy.id, "version": policy.version, "headline_metric": headline},
        "kpis": kpis,
        "waterfall": waterfall,
        "timeline": citation_timeline(session, "researcher", researcher_id, policy),
        "top_citing_institutions": top_citing_institutions(session, "researcher", researcher_id, policy),
        "integrity_flags": detect_integrity_flags(session, "researcher", researcher_id, policy),
        "data_notice": {"has_synthetic": synth > 0, "synthetic_rows": synth},
    }


def institution_report(session, institution_id: int, policy_id: int | None = None) -> dict:
    institution = session.get(Institution, institution_id)
    if institution is None:
        raise KeyError(f"institution {institution_id} not found")
    policy = _policy(session, policy_id)
    kpis = institution_kpis(session, institution_id, policy)
    dup, rep = _waterfall_sums(session, "institution", institution_id)
    headline = policy_value(policy, "headline_metric", "external_only")
    waterfall = build_waterfall(
        raw_rows=kpis["raw_rows"], duplicates_removed=dup, repeats_removed=rep,
        unique_citations=kpis["unique_citations"], self_citations=kpis["self"],
        internal_citations=kpis["internal"], external_citations=kpis["external"],
        headline_metric=headline,
    )
    synth = _synthetic_rows(session)
    return {
        "institution": {"id": institution.id, "name": institution.name, "ror": institution.ror_id},
        "policy": {"id": policy.id, "version": policy.version, "headline_metric": headline},
        "kpis": kpis,
        "waterfall": waterfall,
        "timeline": citation_timeline(session, "institution", institution_id, policy),
        "top_citing_institutions": top_citing_institutions(session, "institution", institution_id, policy),
        "integrity_flags": detect_integrity_flags(session, "institution", institution_id, policy),
        "data_notice": {"has_synthetic": synth > 0, "synthetic_rows": synth},
    }


def waterfall_view(session, scope_type: str, scope_id: int, policy_id: int | None = None) -> dict:
    from app.services.explain import explain_waterfall

    if scope_type == "researcher":
        rep = researcher_report(session, scope_id, policy_id)
    elif scope_type == "institution":
        rep = institution_report(session, scope_id, policy_id)
    else:
        raise KeyError(f"unknown scope_type: {scope_type}")
    return {
        "scope_type": scope_type,
        "scope_id": scope_id,
        "bars": rep["waterfall"],
        "explanations": explain_waterfall(rep["waterfall"]),
    }
