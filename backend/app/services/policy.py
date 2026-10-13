"""Institutional policy engine — PRD 5.6.

Updating a policy bumps its version and recomputes all classifications live.
"""
from app.models import Policy

DEFAULT_POLICY_CONFIG = {
    "citing_authors_considered": "any",
    "self_citation_scope": "author",
    "headline_metric": "external_only",
    "dedup_auto_threshold": 92,
    "dedup_review_min": 80,
    "ring_min_mutual_citations": 4,
    "internal_ratio_flag_threshold": 0.5,
    "concentration_flag_threshold": 0.4,
}


def policy_value(policy, key: str, default=None):
    """Read a config value from a Policy row or a plain config dict."""
    config = policy.config if isinstance(policy, Policy) else (policy or {})
    if not isinstance(config, dict):
        return default
    return config.get(key, DEFAULT_POLICY_CONFIG.get(key, default))


def get_policy(session, policy_id: int) -> Policy | None:
    return session.get(Policy, policy_id)


def get_active_policy(session, institution_id: int | None = None) -> Policy | None:
    q = session.query(Policy).filter_by(is_active=True)
    if institution_id is not None:
        q = q.filter_by(institution_id=institution_id)
    return q.order_by(Policy.version.desc()).first()


def create_policy(session, name: str, config: dict | None = None,
                  institution_id: int | None = None) -> Policy:
    from app.services.classify import classify_all  # local import: classify imports policy

    merged = dict(DEFAULT_POLICY_CONFIG)
    merged.update(config or {})
    # The new policy becomes the only active one: report endpoints resolve
    # the active policy without an institution filter, so two actives would
    # make every default report pick one of them at random.
    session.query(Policy).filter_by(is_active=True).update(
        {"is_active": False}, synchronize_session=False)
    policy = Policy(institution_id=institution_id, name=name, version=1,
                    config=merged, is_active=True)
    session.add(policy)
    session.flush()
    # Compute classifications now: reports filter on policy id + version,
    # so a policy without rows would fail the classification invariant.
    classify_all(session, policy)
    session.flush()
    return policy


def ensure_default_policy(session) -> Policy:
    policy = get_active_policy(session)
    if policy is None:
        policy = create_policy(session, name="default")
    return policy


def update_policy(session, policy_id: int, config_updates: dict) -> Policy:
    """Merge config updates, bump version, recompute classifications live."""
    from app.services.classify import classify_all  # local import: classify imports policy

    policy = get_policy(session, policy_id)
    if policy is None:
        raise ValueError(f"policy {policy_id} not found")
    merged = dict(policy.config or {})
    merged.update(config_updates or {})
    policy.config = merged
    policy.version = (policy.version or 1) + 1
    session.flush()
    classify_all(session, policy)
    session.flush()
    return policy
