"""Optional LLM assist — PRD 11.8 (F17), powered by Groq (free tier).

Used ONLY when ENABLE_LLM_ASSIST=true and GROQ_API_KEY is set.
Suggestions are shown to the human reviewer; nothing is ever auto-applied.
Every function degrades gracefully to a safe default when disabled.
"""
import json
import os

# Non-reasoning chat model with native JSON mode — safe default for strict-JSON
# outputs. Override with LLM_MODEL (e.g. "llama-3.1-8b-instant" for max speed).
DEFAULT_MODEL = os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile")


def llm_enabled() -> bool:
    return (
        os.environ.get("ENABLE_LLM_ASSIST", "false").lower() == "true"
        and bool(os.environ.get("GROQ_API_KEY"))
    )


def _client():
    if not llm_enabled():
        return None
    from groq import Groq

    return Groq(api_key=os.environ.get("GROQ_API_KEY"))


def suggest_merge(record_a: dict, record_b: dict) -> dict:
    """Ask the model whether two records are the same paper.

    Returns {"same_paper": bool, "confidence": 0-1, "reason": str}.
    Never raises; returns an 'unavailable' verdict when disabled.
    """
    fallback = {"same_paper": False, "confidence": 0.0, "reason": "llm_unavailable"}
    client = _client()
    if client is None:
        return fallback
    prompt = (
        "You are a bibliographic deduplication assistant. Decide whether the two "
        "records below describe the SAME research paper. Consider titles, DOIs, "
        "years, venues and author overlap. Preprints and their published versions "
        "count as the same paper; 'Part 1' vs 'Part 2' do NOT.\n"
        "Reply with strict JSON only: "
        '{"same_paper": bool, "confidence": 0-1, "reason": str}\n\n'
        f"Record A: {json.dumps(record_a, ensure_ascii=False)}\n"
        f"Record B: {json.dumps(record_b, ensure_ascii=False)}"
    )
    try:
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=300,
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content)
        if not isinstance(data, dict):
            return fallback
        return {
            "same_paper": bool(data.get("same_paper", False)),
            "confidence": max(0.0, min(1.0, float(data.get("confidence", 0.0)))),
            "reason": str(data.get("reason", ""))[:500],
        }
    except Exception:
        return fallback


def suggest_intent(sentences: list) -> str | None:
    """Suggest a citation intent label for mention sentences, or None."""
    client = _client()
    if client is None or not sentences:
        return None
    prompt = (
        "Classify how the cited paper is used in these citing sentences. Reply with "
        "exactly one word: background, uses, supports, extends, contrasts, or unclear.\n\n"
        + "\n".join(f"- {s}" for s in sentences[:5])
    )
    try:
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=20,
        )
        label = response.choices[0].message.content.strip().lower()
        return label if label in ("background", "uses", "supports", "extends", "contrasts", "unclear") else None
    except Exception:
        return None
