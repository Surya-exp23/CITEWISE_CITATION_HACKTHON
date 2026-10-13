"""Plain-English explanations — deterministic templates.

Every classification and every waterfall step gets a 1-2 sentence explanation
so a non-technical committee member can read the audit trail.
"""
from app.services.intent import INTENT_PRIORITY

_INTENT_PHRASES = {
    "background": "provides background context",
    "uses": "is used for its method",
    "supports": "is cited in support of the findings",
    "extends": "is built upon or extended",
    "contrasts": "is contrasted with or challenged",
    "unclear": "has no clear citation role from the available text",
}


def explain_classification(klass: str, reason: dict) -> str:
    """One or two sentences explaining why a citation got its class."""
    reason = reason or {}
    rule = reason.get("rule", "")
    if klass == "self":
        who = reason.get("matched_author") or "an author"
        extra = " (matched by name only — worth a human check)" if reason.get("note") == "name_match_fallback" else ""
        return f"Counted as a self-citation: {who} authored both the citing and the cited paper.{extra}"
    if klass == "internal":
        ror = reason.get("matched_ror") or "the same institution"
        who = reason.get("citing_author") or "a citing author"
        return f"Counted as internal: {who} is affiliated with {ror}, an institution the cited researcher was affiliated with on the cited paper."
    if rule == "no_shared_author_or_institution":
        note = " Some citing affiliations could not be resolved." if reason.get("note") == "unresolved_affiliation" else ""
        return "Counted as external: none of the citing authors share an author or institution with the cited paper." + note
    return f"Classified as {klass} by rule {rule}."


def explain_intent(intent: str) -> str:
    phrase = _INTENT_PHRASES.get(intent, _INTENT_PHRASES["unclear"])
    return f"This citation {phrase}."


def explain_waterfall(waterfall: list) -> list:
    """One plain-English line per waterfall bar."""
    lines = []
    values = {b["label"]: b["value"] for b in waterfall}
    if "Raw rows" in values:
        lines.append(f"Started with {values['Raw rows']} raw citation rows exactly as received from the sources.")
    if "Duplicate records removed" in values:
        lines.append(f"Removed {abs(values['Duplicate records removed'])} rows contributed by duplicate paper records that were merged.")
    if "Repeated mentions collapsed" in values:
        lines.append(f"Collapsed {abs(values['Repeated mentions collapsed'])} repeated in-text mentions: one citing paper counts once no matter how often it mentions a paper.")
    if "Unique citations" in values:
        lines.append(f"{values['Unique citations']} unique citation edges remain after cleaning.")
    if "Self-citations" in values:
        lines.append(f"Excluded {abs(values['Self-citations'])} self-citations (the researcher cited their own work).")
    if "Internal citations" in values:
        lines.append(f"Excluded {abs(values['Internal citations'])} internal citations from the researcher's own institution(s).")
    for b in waterfall:
        if b.get("total"):
            lines.append(f"{b['value']} verified citations — the headline number. Every one of them can be clicked through to its evidence.")
    return lines


def intent_label(intent: str) -> str:
    return intent if intent in INTENT_PRIORITY else "unclear"
