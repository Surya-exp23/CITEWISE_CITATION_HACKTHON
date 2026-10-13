"""Pydantic v2 request/response models. Researcher report shape is PRD 12.1."""
from typing import Any

from pydantic import BaseModel, Field


# --- shared ---

class ErrorBody(BaseModel):
    error: dict = Field(examples=[{"code": "not_found", "message": "No such researcher"}])


class Page(BaseModel):
    page: int = 1
    page_size: int = 50


# --- institutions / researchers ---

class InstitutionOut(BaseModel):
    id: int
    ror_id: str | None
    name: str
    country_code: str | None


class ResearcherOut(BaseModel):
    id: int
    openalex_id: str | None
    orcid: str | None
    display_name: str


class WaterfallBar(BaseModel):
    label: str
    value: int
    subtotal: bool = False
    total: bool = False


class PolicyOut(BaseModel):
    id: int
    institution_id: int | None
    name: str | None
    version: int
    config: dict
    is_active: bool


class ResearcherKpis(BaseModel):
    papers: int
    raw_rows: int
    unique_citations: int
    self: int
    internal: int
    external: int
    verified_total: int
    h_index_raw: int
    h_index_verified: int
    i10_verified: int
    internal_ratio: float
    self_ratio: float


class TimelineYear(BaseModel):
    year: int
    external: int
    internal: int
    self: int


class CitingInstitution(BaseModel):
    name: str | None
    ror: str | None
    count: int


class DataNotice(BaseModel):
    has_synthetic: bool
    synthetic_rows: int


class ResearcherReport(BaseModel):
    """PRD 12.1 shape."""
    researcher: dict
    policy: dict
    kpis: ResearcherKpis
    waterfall: list[WaterfallBar]
    timeline: list[TimelineYear]
    top_citing_institutions: list[CitingInstitution]
    integrity_flags: list[dict]
    data_notice: DataNotice


class PaperRow(BaseModel):
    work_id: int
    title: str
    year: int | None
    doi: str | None
    raw_rows: int
    unique: int
    self: int
    internal: int
    external: int
    verified: int


class LeaderboardRow(BaseModel):
    id: int
    name: str
    papers: int
    raw_citations: int
    verified_citations: int
    h_index_verified: int


# --- citations / evidence ---

class CitationOut(BaseModel):
    id: int
    citing_work_id: int
    cited_work_id: int
    citing_title: str | None = None
    cited_title: str | None = None
    year: int | None = None
    mention_count: int
    raw_rows_total: int
    duplicates_removed: int
    repeats_removed: int
    klass: str | None = None
    intent: str | None = None


class EvidenceOut(BaseModel):
    citation_id: int
    record: dict
    sha256: str


class WaterfallExplain(BaseModel):
    label: str
    value: int
    explanation: str


class WaterfallOut(BaseModel):
    scope_type: str
    scope_id: int
    bars: list[WaterfallBar]
    explanations: list[str]


# --- policies ---

class PolicyCreate(BaseModel):
    name: str = "custom"
    institution_id: int | None = None
    config: dict | None = None


class PolicyUpdate(BaseModel):
    config: dict


# --- review ---

class ReviewItemOut(BaseModel):
    id: int
    item_type: str
    payload: dict
    score: float | None
    status: str
    decided_at: str | None = None


class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")


class ReviewSuggestionOut(BaseModel):
    item_id: int
    ai_suggestion: dict  # {same_paper, confidence, reason}
    llm_enabled: bool


# --- integrity ---

class IntegrityFlagOut(BaseModel):
    flag_type: str
    scope_type: str | None
    scope_id: int | None
    severity: str | None
    details: dict


# --- reports / verify ---

class ReportCreate(BaseModel):
    scope_type: str = Field(pattern="^(researcher|institution)$")
    scope_id: int
    policy_id: int | None = None


class ReportOut(BaseModel):
    id: int
    scope_type: str
    scope_id: int
    policy_id: int | None
    policy_version: int | None
    root_hash: str
    created_at: str | None = None


class VerifyOut(BaseModel):
    stored_root: str | None
    recomputed_root: str | None
    status: str
    generated_at: str | None = None
    record_count: int


# --- ingest ---

class IngestJobOut(BaseModel):
    id: str
    status: str
    stages: dict = {}
    summary: dict = {}


class CsvUploadOut(BaseModel):
    job: IngestJobOut
    rows_received: int
    rows_loaded: int
    errors: list[dict]
