"""Identifier and text normalization — PRD section 5.1.

All functions are pure and deterministic.
"""
import re
import unicodedata

from unidecode import unidecode

# British -> American spelling variants. Applied as prefix matches so inflected
# forms are covered too (tumours -> tumors, oesophageal -> esophageal).
_BRITISH_TO_AMERICAN = [
    ("randomised", "randomized"),
    ("tumour", "tumor"),
    ("haemoglobin", "hemoglobin"),
    ("oesophag", "esophag"),
    ("behaviour", "behavior"),
    ("colour", "color"),
    ("centre", "center"),
    ("organise", "organize"),
    ("organised", "organized"),
    ("analyse", "analyze"),
    ("analysed", "analyzed"),
    ("cheque", "check"),
    ("diarrhoea", "diarrhea"),
    ("aetiolog", "etiolog"),
    ("anaemi", "anemi"),
    ("paediatr", "pediatr"),
    ("gynaecolog", "gynecolog"),
    ("orthopaed", "orthoped"),
    ("oesophag", "esophag"),
    ("leukaemi", "leukemi"),
    ("fibre", "fiber"),
    ("litre", "liter"),
    ("metre", "meter"),
    ("generalise", "generalize"),
    ("specialise", "specialize"),
    ("hospitalise", "hospitalize"),
    ("immunise", "immunize"),
    ("recognise", "recognize"),
    ("utilise", "utilize"),
    ("foetal", "fetal"),
]

_DOI_PREFIXES = ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:")


def normalize_doi(doi: str | None) -> str | None:
    """Lowercase; strip doi.org / dx.doi.org / doi: prefixes; trim whitespace
    and trailing punctuation."""
    if not doi:
        return None
    d = doi.strip().lower()
    for prefix in _DOI_PREFIXES:
        if d.startswith(prefix):
            d = d[len(prefix):]
            break
    return d.strip().rstrip(".,;:")


def normalize_pmid(pmid: str | None) -> str | None:
    """Digits only."""
    if not pmid:
        return None
    digits = re.sub(r"\D", "", str(pmid))
    return digits or None


def normalize_pmcid(pmcid: str | None) -> str | None:
    """Uppercase PMC + digits (e.g. 'pmc12345' -> 'PMC12345')."""
    if not pmcid:
        return None
    digits = re.sub(r"\D", "", str(pmcid))
    return f"PMC{digits}" if digits else None


def _apply_spelling_map(text: str) -> str:
    for british, american in _BRITISH_TO_AMERICAN:
        text = re.sub(r"\b" + re.escape(british), american, text)
    return text


def normalize_title(title: str | None) -> str:
    """Unicode NFKD, remove diacritics, lowercase, British->American spelling,
    punctuation -> space, collapse whitespace."""
    if not title:
        return ""
    text = unicodedata.normalize("NFKD", title)
    text = unidecode(text)
    text = text.lower()
    text = _apply_spelling_map(text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_name_part(part: str | None) -> str:
    """Normalized surname token for blocking and keys."""
    if not part:
        return ""
    text = unidecode(unicodedata.normalize("NFKD", part)).lower()
    return re.sub(r"[^a-z]", "", text)


def author_key(last_name: str | None, first_name: str | None = None) -> str:
    """Normalized last name + first initial, e.g. 'sharma_a'."""
    last = normalize_name_part(last_name)
    initial = normalize_name_part(first_name)[:1] if first_name else ""
    return f"{last}_{initial}" if initial else last
