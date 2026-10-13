// Plain-English explanations, ported from backend explain.py.

export function explainClassification(klass, reason = {}) {
  const rule = reason.rule || "";
  if (klass === "self") {
    const who = reason.matched_author || "an author";
    const extra =
      reason.note === "name_match_fallback" ? " (matched by name only — worth a human check)" : "";
    return `Counted as a self-citation: ${who} authored both the citing and the cited paper.${extra}`;
  }
  if (klass === "internal") {
    const ror = reason.matched_ror || "the same institution";
    const who = reason.citing_author || "a citing author";
    return `Counted as internal: ${who} is affiliated with ${ror}, an institution the cited researcher was affiliated with on the cited paper.`;
  }
  if (rule === "no_shared_author_or_institution") {
    const note =
      reason.note === "unresolved_affiliation" ? " Some citing affiliations could not be resolved." : "";
    return "Counted as external: none of the citing authors share an author or institution with the cited paper." + note;
  }
  return `Classified as ${klass} by rule ${rule}.`;
}

const INTENT_PHRASES = {
  background: "gives background for the citing work",
  uses: "is used by the citing work (method, data, or tool)",
  supports: "is supported by the citing work's findings",
  extends: "is extended by the citing work",
  contrasts: "is contrasted with the citing work's findings",
  unclear: "has an unclear role in the citing work",
};

export function explainIntent(intent) {
  return `This citation ${INTENT_PHRASES[intent] || INTENT_PHRASES.unclear}.`;
}

export function intentLabel(intent) {
  return intent ? intent.charAt(0).toUpperCase() + intent.slice(1) : "—";
}
