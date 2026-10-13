"""Citation intent classification — AI module.

Primary path: deterministic cue-phrase heuristics over the mention sentences
(fast, offline, no API key). Optional LLM path used only when
ENABLE_LLM_ASSIST=true. Labels: background | uses | supports | extends |
contrasts | unclear.

Priority order resolves conflicts (contrasts beats supports, etc.).
"""
import os
import re

INTENT_PRIORITY = ("contrasts", "supports", "extends", "uses", "background", "unclear")

_CUES = {
    "contrasts": [
        r"\bhowever\b", r"\bin contrast\b", r"\bcontrary to\b", r"\bdisagree",
        r"\bfailed to replicat", r"\bcould not replicat", r"\bno significant\b",
        r"\brefut", r"\bchalleng", r"\bquestion(s|ed)? the\b", r"\bunlike\b",
        r"\binconsistent with\b", r"\bcontradict",
    ],
    "supports": [
        r"\bconsistent with\b", r"\bin agreement with\b", r"\bconfirm(s|ed|ing)?\b",
        r"\bsupport(s|ed|ing)?\b", r"\bcorroborat", r"\breplicat",
        r"\bin line with\b", r"\bin accordance with\b", r"\bvalidate[sd]?\b",
    ],
    "extends": [
        r"\bbuild(s|ing)? (on|upon)\b", r"\bextend(s|ed|ing)?\b", r"\bfurther\b",
        r"\bwe adapt", r"\bfollowing\b", r"\bbased on\b", r"\bextend the\b",
        r"\bgeneraliz", r"\bimprov(e|ed|ing|ement)",
    ],
    "uses": [
        r"\bwe used\b", r"\busing\b", r"\bwe applied\b", r"\bemploy(ed|ing)?\b",
        r"\bmethod(s)?\b", r"\bprotocol\b", r"\baccording to\b", r"\badopted\b",
        r"\bperformed (as|using)\b",
    ],
    "background": [
        r"\bpreviously\b", r"\bhas been shown\b", r"\bhave been shown\b",
        r"\bit is known\b", r"\bit is well known\b", r"\breview(s|ed)?\b",
        r"\breported\b", r"\bdescribed\b", r"\bestablished\b",
    ],
}

_COMPILED = {intent: [re.compile(p) for p in pats] for intent, pats in _CUES.items()}


def classify_intent(sentences: list, use_llm: bool = False) -> str:
    """Classify the intent of a citation from its mention sentences."""
    if use_llm and os.environ.get("ENABLE_LLM_ASSIST", "false").lower() == "true":
        try:
            from app.services.llm import suggest_intent

            result = suggest_intent([s for s in sentences if s])
            if result in INTENT_PRIORITY:
                return result
        except Exception:
            pass
    text = " ".join(s for s in sentences if s).lower()
    if not text.strip():
        return "unclear"
    for intent in INTENT_PRIORITY:
        if intent == "unclear":
            continue
        if any(p.search(text) for p in _COMPILED[intent]):
            return intent
    return "background"
