"""Pydantic schemas for the Career Assistant QA feature (Stage 4A + 4B).

These schemas cover:
- ``CareerAssistantQACreate``: the user-facing request to ask a question.
- ``KnowledgeQAWorkflowInput``: the strictly-typed payload sent to the
  Dify knowledge QA workflow (question + retrieved context chunks +
  optional personal context chunks for Stage 4B).
- ``KnowledgeQAWorkflowOutput``: the strictly-typed response expected from
  the workflow (answer + structured citations).
- ``CareerAssistantQARead`` / ``CareerAssistantQAListItemRead``: API
  response models for reading a single QA run or listing history.
- ``KnowledgeDocumentRead`` / ``KnowledgeDocumentCreate``: admin-facing
  models for managing knowledge base documents.

All schemas use ``extra="forbid"`` to reject unexpected fields, matching
the project's strict-schema convention.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Workflow input / output (Dify knowledge QA contract)
# ---------------------------------------------------------------------------


class KnowledgeQAContextChunk(StrictSchema):
    """A retrieved knowledge chunk sent to the workflow as context.

    ``document_id`` allows ``0`` for the synthetic placeholder chunk
    used when only personal context is available (Stage 4B); real
    knowledge documents always have ``document_id >= 1``.
    """

    document_id: int = Field(ge=0)
    title: str = Field(min_length=1, max_length=240)
    category: str = Field(min_length=1, max_length=80)
    chunk_text: str = Field(min_length=1, max_length=4000)
    chunk_index: int = Field(ge=0)
    page_number: int | None = Field(default=None, ge=1)
    paragraph_index: int | None = Field(default=None, ge=0)
    score: float = Field(ge=0.0, le=1.0)


class PersonalContextChunk(StrictSchema):
    """A user-private data snippet sent to the workflow as personal context.

    Introduced in Stage 4B for personalised QA. Unlike knowledge chunks
    (which come from the shared FAISS index), personal chunks are derived
    from the user's own resume, match reports and applications.
    ``source_type`` identifies the origin so the backend
    can build citations with correct provenance.
    """

    source_type: Literal["resume", "match_report", "application"]
    source_id: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=240)
    category: str = Field(min_length=1, max_length=80)
    chunk_text: str = Field(min_length=1, max_length=4000)
    chunk_index: int = Field(ge=0)
    score: float = Field(default=1.0, ge=0.0, le=1.0)


class KnowledgeQAGeneration(StrictSchema):
    """Provenance metadata for a knowledge QA generation run."""

    workflow_version: str = Field(min_length=1, max_length=80)
    workflow_run_id: str | None = Field(default=None, max_length=160)
    provider: str = Field(default="dify", min_length=1, max_length=40)
    latency_ms: int = Field(default=0, ge=0)
    prompt_version: str = Field(default="career-rag-v1", min_length=1, max_length=80)


class KnowledgeQAWorkflowInput(StrictSchema):
    """Strict payload sent to the Dify knowledge QA workflow.

    The backend performs FAISS retrieval first and passes only the
    ranked context chunks to Dify. Dify is responsible solely for
    generating the answer and citation mapping; it does not retrieve
    documents itself. This keeps citations fully under backend control.

    Stage 4B adds an optional ``personal_context`` list so the workflow
    can also reference the user's private data (resume, matches, plans,
    applications). When non-empty, ``schema_version`` is elevated to
    ``career-assistant-personalized-input-v1``.
    """

    schema_version: Literal[
        "career-assistant-knowledge-input-v1",
        "career-assistant-personalized-input-v1",
    ] = "career-assistant-knowledge-input-v1"
    user_id: int = Field(ge=1)
    question: str = Field(min_length=1, max_length=2000)
    context_chunks: list[KnowledgeQAContextChunk] = Field(min_length=1, max_length=10)
    personal_context: list[PersonalContextChunk] = Field(
        default_factory=list,
        max_length=10,
    )
    # Deterministic query-decomposition diagnostics. These fields tell Dify
    # which requested entities have direct retrieved evidence without exposing
    # internal index paths or embeddings.
    requested_entities: list[str] = Field(default_factory=list, max_length=10)
    retrieved_entities: list[str] = Field(default_factory=list, max_length=10)
    missing_entities: list[str] = Field(default_factory=list, max_length=10)
    user_locale: str = Field(default="zh-CN", min_length=2, max_length=16)


class KnowledgeQACitation(StrictSchema):
    """A citation reference produced by the Fake provider for tests.

    The real Dify workflow returns ``used_citation_keys`` (a list of
    ``"doc-<id>-chunk-<index>"`` strings) instead of structured citation
    objects. The backend enriches these keys with full chunk provenance
    via ``_enrich_citations``. This schema is only used by
    ``FakeKnowledgeQAProvider`` to keep test assertions readable.
    """

    document_id: int = Field(ge=1)
    chunk_index: int = Field(ge=0)
    quote: str = Field(default="", max_length=600)


class KnowledgeQAWorkflowOutput(StrictSchema):
    """Strict response expected from the Dify knowledge QA workflow.

    Dify returns ``used_citation_keys`` (strings) and an
    ``insufficient_evidence`` flag rather than structured citation objects.
    The backend uses these keys to look up the full chunk provenance from
    the retrieval stage and build ``CareerAssistantQACitationRead`` objects.
    """

    schema_version: Literal["career-assistant-knowledge-v1"] = "career-assistant-knowledge-v1"
    answer: str = Field(min_length=1, max_length=8000)
    used_citation_keys: list[str] = Field(default_factory=list, max_length=10)
    insufficient_evidence: bool = False
    generation: KnowledgeQAGeneration


# ---------------------------------------------------------------------------
# Provider result / attempt
# ---------------------------------------------------------------------------


class KnowledgeQAProviderAttempt(StrictSchema):
    """One attempt within the provider retry chain.

    ``status`` is the provider's own semantic status for this attempt
    ("succeeded" / "failed"), kept distinct from the Dify-side diagnostic
    fields (``error``, ``total_steps``, ``elapsed_time``, ``outputs_keys``)
    which describe the Dify workflow run itself.
    """

    sequence: int = Field(ge=1)
    http_status: int | None = Field(default=None, ge=100, le=599)
    status: str = Field(min_length=1, max_length=40)
    latency_ms: int = Field(default=0, ge=0)
    retried: bool = False
    error_code: str | None = Field(default=None, max_length=80)
    error_message: str | None = Field(default=None, max_length=240)
    workflow_run_id: str | None = Field(default=None, max_length=160)
    workflow_id: str | None = Field(default=None, max_length=160)
    error: str | None = Field(default=None, max_length=240)
    total_steps: int | None = Field(default=None, ge=0)
    elapsed_time: float | None = Field(default=None, ge=0)
    outputs_keys: list[str] = Field(default_factory=list)


class KnowledgeQAProviderResult(StrictSchema):
    """The full result of a knowledge QA provider call."""

    output: KnowledgeQAWorkflowOutput
    raw_output: dict[str, Any]
    attempts: list[KnowledgeQAProviderAttempt] = Field(min_length=1)
    # Safe audit information about the exact evidence shape submitted to the
    # provider.  This intentionally excludes credentials and only retains a
    # bounded preview of retrieved text.
    request_summary: dict[str, JsonValue] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# API request / response models
# ---------------------------------------------------------------------------


class CareerAssistantQACreate(StrictSchema):
    """User-facing request to ask a question.

    ``scope`` controls which context sources the backend retrieves before
    calling the Dify workflow (Stage 4B):
    - ``auto`` (default): search both the shared knowledge base and the
      user's private data.
    - ``knowledge``: search only the shared knowledge base.
    - ``personal``: search only the user's private data.
    """

    question: str = Field(min_length=1, max_length=2000)
    scope: Literal["auto", "knowledge", "personal"] = "auto"


class CareerAssistantQACitationRead(StrictSchema):
    """A citation rendered in the API response, with full provenance.

    For knowledge-base citations ``document_id`` is set and
    ``source_type`` is ``"knowledge"``. For personal-data citations
    (Stage 4B) ``document_id`` may be ``0`` and ``source_type`` /
    ``source_id`` identify the user-private record instead.
    """

    source_type: Literal["knowledge", "resume", "match_report", "application"] = (
        "knowledge"
    )
    source_id: int = Field(default=0, ge=0)
    document_id: int = Field(default=0, ge=0)
    title: str = Field(min_length=1, max_length=240)
    category: str = Field(min_length=1, max_length=80)
    chunk_index: int = Field(ge=0)
    chunk_text: str = Field(min_length=1, max_length=4000)
    quote: str = Field(default="", max_length=600)
    page_number: int | None = Field(default=None, ge=1)
    paragraph_index: int | None = Field(default=None, ge=0)
    score: float = Field(ge=0.0, le=1.0)


class CareerAssistantQARead(StrictSchema):
    """Full QA run response."""

    id: int
    user_id: int
    question: str
    answer: str | None = None
    status: str
    citations: list[CareerAssistantQACitationRead] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    finished_at: datetime | None = None


class CareerAssistantQAListItemRead(StrictSchema):
    """Compact QA run item for list views."""

    id: int
    question: str
    status: str
    answer: str | None = None
    created_at: datetime
    finished_at: datetime | None = None


class CareerAssistantQAListRead(StrictSchema):
    """Paginated list of QA runs for the current user."""

    items: list[CareerAssistantQAListItemRead]
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)


class CareerAssistantQAEvent(StrictSchema):
    """One persisted event in a QA run, replayed over SSE."""

    id: int
    event: str
    run_id: int
    node: str | None = None
    status: str
    timestamp: datetime
    duration_ms: int | None = None
    summary: dict[str, JsonValue] = Field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    answer: str | None = None
    citations: list[dict[str, JsonValue]] = Field(default_factory=list)


class CareerAssistantQAEventTicket(StrictSchema):
    """Short-lived ticket authorising one SSE connection."""

    ticket: str = Field(min_length=20)
    expires_at: datetime


# ---------------------------------------------------------------------------
# Knowledge document admin models
# ---------------------------------------------------------------------------


class KnowledgeDocumentRead(StrictSchema):
    """Admin-facing knowledge document response."""

    id: int
    title: str
    category: str
    status: str
    chunk_count: int
    content_hash: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    indexed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class KnowledgeDocumentListRead(StrictSchema):
    """Paginated list of knowledge documents."""

    items: list[KnowledgeDocumentRead]
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)


class KnowledgeDocumentReindexResult(StrictSchema):
    """Result of triggering a re-index of one document."""

    document_id: int
    status: str
    chunk_count: int
    reused: bool
