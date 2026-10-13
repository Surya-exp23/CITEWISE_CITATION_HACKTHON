"""SQLAlchemy models for CiteWise — every table from PRD section 10.

SQLite-compatible: JSON instead of JSONB, Integer autoincrement PKs,
DateTime instead of TIMESTAMPTZ. Table and column names match the PRD exactly.
Two additive columns beyond the PRD: citations.intent and mentions.intent
(AI citation-intent classification, see services/intent.py).
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Institution(Base):
    __tablename__ = "institutions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ror_id: Mapped[str | None] = mapped_column(Text, unique=True)
    openalex_id: Mapped[str | None] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    country_code: Mapped[str | None] = mapped_column(Text)
    aliases: Mapped[list] = mapped_column(JSON, default=list)


class Author(Base):
    __tablename__ = "authors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    openalex_id: Mapped[str | None] = mapped_column(Text, unique=True)
    orcid: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    name_key: Mapped[str | None] = mapped_column(Text)


class Work(Base):
    """Canonical paper: one row per merged work."""

    __tablename__ = "works"
    __table_args__ = (
        Index("works_doi_uq", "doi", unique=True, sqlite_where=text("doi IS NOT NULL")),
        Index("works_pmid_uq", "pmid", unique=True, sqlite_where=text("pmid IS NOT NULL")),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    openalex_id: Mapped[str | None] = mapped_column(Text, unique=True)
    doi: Mapped[str | None] = mapped_column(Text)
    pmid: Mapped[str | None] = mapped_column(Text)
    pmcid: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    title_norm: Mapped[str] = mapped_column(Text, nullable=False)
    year: Mapped[int | None] = mapped_column(Integer)
    venue: Mapped[str | None] = mapped_column(Text)
    pub_type: Mapped[str | None] = mapped_column(Text)
    is_preprint: Mapped[bool] = mapped_column(Boolean, default=False)
    is_retracted: Mapped[bool] = mapped_column(Boolean, default=False)
    mesh_terms: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime, default=_utcnow)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)

    authorships: Mapped[list["Authorship"]] = relationship(back_populates="work", cascade="all, delete-orphan")
    aliases: Mapped[list["WorkAlias"]] = relationship(back_populates="work", cascade="all, delete-orphan")


class WorkAlias(Base):
    """Raw record merged into a canonical work. The canonical record itself is
    stored with merge_reason='primary' so every raw_record_id resolves uniformly."""

    __tablename__ = "work_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_id: Mapped[int] = mapped_column(ForeignKey("works.id"), nullable=False)
    raw_record_id: Mapped[str] = mapped_column(Text, nullable=False)
    raw_title: Mapped[str | None] = mapped_column(Text)
    raw_doi: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(Text)
    merge_reason: Mapped[str | None] = mapped_column(Text)
    merge_confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    fuzzy_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    status: Mapped[str] = mapped_column(Text, default="auto")
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)

    work: Mapped["Work"] = relationship(back_populates="aliases")


class Authorship(Base):
    __tablename__ = "authorships"
    __table_args__ = (
        Index("authorships_work_idx", "work_id"),
        Index("authorships_author_idx", "author_id"),
        Index("authorships_inst_idx", "institution_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_id: Mapped[int] = mapped_column(ForeignKey("works.id"), nullable=False)
    author_id: Mapped[int] = mapped_column(ForeignKey("authors.id"), nullable=False)
    institution_id: Mapped[int | None] = mapped_column(ForeignKey("institutions.id"))
    position: Mapped[str | None] = mapped_column(Text)
    raw_affiliation: Mapped[str | None] = mapped_column(Text)

    work: Mapped["Work"] = relationship(back_populates="authorships")
    author: Mapped["Author"] = relationship()
    institution: Mapped["Institution | None"] = relationship()


class RawCitationRow(Base):
    """Citation rows exactly as received."""

    __tablename__ = "raw_citation_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    raw_citing_record_id: Mapped[str] = mapped_column(Text, nullable=False)
    raw_cited_record_id: Mapped[str] = mapped_column(Text, nullable=False)
    row_kind: Mapped[str] = mapped_column(Text, nullable=False)
    context_sentence: Mapped[str | None] = mapped_column(Text)
    section: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(Text)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)


class Citation(Base):
    """Unique (citing, cited) edge. intent is additive beyond the PRD."""

    __tablename__ = "citations"
    __table_args__ = (
        UniqueConstraint("citing_work_id", "cited_work_id", name="citations_pair_uq"),
        CheckConstraint("citing_work_id <> cited_work_id", name="citations_no_self_cite"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    citing_work_id: Mapped[int] = mapped_column(ForeignKey("works.id"), nullable=False)
    cited_work_id: Mapped[int] = mapped_column(ForeignKey("works.id"), nullable=False)
    mention_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    raw_rows_total: Mapped[int] = mapped_column(Integer, nullable=False)
    duplicates_removed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    repeats_removed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    intent: Mapped[str | None] = mapped_column(Text)

    mentions: Mapped[list["Mention"]] = relationship(back_populates="citation", cascade="all, delete-orphan")


class Mention(Base):
    __tablename__ = "mentions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    citation_id: Mapped[int] = mapped_column(ForeignKey("citations.id"))
    sentence: Mapped[str | None] = mapped_column(Text)
    section: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(Text)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    intent: Mapped[str | None] = mapped_column(Text)

    citation: Mapped["Citation"] = relationship(back_populates="mentions")


class Policy(Base):
    __tablename__ = "policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    institution_id: Mapped[int | None] = mapped_column(ForeignKey("institutions.id"))
    name: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    config: Mapped[dict] = mapped_column(JSON, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class CitationClassification(Base):
    __tablename__ = "citation_classifications"
    __table_args__ = (
        UniqueConstraint(
            "citation_id", "scope_type", "scope_id", "policy_id", "policy_version",
            name="classifications_scope_uq",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    citation_id: Mapped[int] = mapped_column(ForeignKey("citations.id"))
    scope_type: Mapped[str] = mapped_column(Text, nullable=False)
    scope_id: Mapped[int | None] = mapped_column(Integer)
    policy_id: Mapped[int | None] = mapped_column(ForeignKey("policies.id"))
    policy_version: Mapped[int | None] = mapped_column(Integer)
    klass: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[dict] = mapped_column(JSON, nullable=False)


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    citation_id: Mapped[int] = mapped_column(ForeignKey("citations.id"))
    scope_type: Mapped[str | None] = mapped_column(Text)
    scope_id: Mapped[int | None] = mapped_column(Integer)
    record: Mapped[dict] = mapped_column(JSON, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=_utcnow)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope_type: Mapped[str] = mapped_column(Text, nullable=False)
    scope_id: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_id: Mapped[int | None] = mapped_column(ForeignKey("policies.id"))
    policy_version: Mapped[int | None] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    root_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=_utcnow)


class ReviewItem(Base):
    __tablename__ = "review_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    status: Mapped[str] = mapped_column(Text, default="pending")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)


class RejectedMerge(Base):
    __tablename__ = "rejected_merges"

    raw_record_a: Mapped[str] = mapped_column(Text, primary_key=True)
    raw_record_b: Mapped[str] = mapped_column(Text, primary_key=True)


class IntegrityFlag(Base):
    __tablename__ = "integrity_flags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    flag_type: Mapped[str] = mapped_column(Text, nullable=False)
    scope_type: Mapped[str | None] = mapped_column(Text)
    scope_id: Mapped[int | None] = mapped_column(Integer)
    severity: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, nullable=False)
