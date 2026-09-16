"""Schemas for the optional chat-based AI mock interview feature.

The contracts here govern the data sent to and received from the Dify
"CareerPilot 模拟面试" workflow. They are intentionally strict
(``extra="forbid"``) so fabrication attempts from the LLM surface as
Pydantic validation errors instead of silently producing interview
questions that reference unevidenced skills or experiences.

Three workflow calls are modeled:

1. **Plan generation** — given resume/job/match context, produce an
   interview plan with N questions (N >= 3, N <= 8).
2. **Chat turn** — advance the evidence-grounded conversation.
3. **Final evaluation** — evaluate the complete chat transcript.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class InterviewType(StrEnum):
    """The type of mock interview, per PROJECT_SPEC section 13."""

    COMPREHENSIVE = "COMPREHENSIVE"
    TECHNICAL = "TECHNICAL"
    BEHAVIORAL = "BEHAVIORAL"
    PROJECT = "PROJECT"
    HR = "HR"


class InterviewStatus(StrEnum):
    """The lifecycle of an interview session.

    * ``PLANNED`` — session created, plan + questions generated, waiting
      for the user to start answering.
    * ``IN_PROGRESS`` — at least one answer has been submitted.
    * ``COMPLETED`` — all main questions answered; report not yet
      generated.
    * ``REPORTED`` — final report generated.
    * ``FAILED`` — plan generation failed; no questions available.
    """

    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    REPORTED = "REPORTED"
    FAILED = "FAILED"


class InterviewQuestionType(StrEnum):
    """The category of an interview question."""

    OPENING = "OPENING"
    TECHNICAL = "TECHNICAL"
    BEHAVIORAL = "BEHAVIORAL"
    PROJECT_DEEP_DIVE = "PROJECT_DEEP_DIVE"
    SITUATIONAL = "SITUATIONAL"
    CLOSING = "CLOSING"


# ---------------------------------------------------------------------------
# Shared evidence-grounded input blocks
# ---------------------------------------------------------------------------


class InterviewResumeInput(StrictSchema):
    resume_version_id: int = Field(ge=1)
    summary: str = Field(default="", max_length=4000)
    education: list[dict[str, JsonValue]] = Field(default_factory=list, max_length=20)
    experiences: list[dict[str, JsonValue]] = Field(default_factory=list, max_length=40)
    projects: list[dict[str, JsonValue]] = Field(default_factory=list, max_length=40)
    skills: list[dict[str, JsonValue]] = Field(default_factory=list, max_length=80)


class InterviewJobInput(StrictSchema):
    job_id: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=240)
    company: str = Field(min_length=1, max_length=240)
    summary: str = Field(default="", max_length=8000)
    source_name: str = Field(default="", max_length=120)
    source_url: str | None = Field(default=None, max_length=1000)
    information_completeness: float = Field(default=0.0, ge=0, le=1)
    is_summary_only: bool = False


class InterviewMatchReportInput(StrictSchema):
    report_id: int = Field(ge=1)
    final_score: float | None = Field(default=None, ge=0, le=100)
    matched_skills: list[dict[str, JsonValue]] = Field(default_factory=list, max_length=80)
    partial_skills: list[dict[str, JsonValue]] = Field(default_factory=list, max_length=80)
    missing_skills: list[dict[str, JsonValue]] = Field(default_factory=list, max_length=80)
    blocking_risks: list[dict[str, JsonValue]] = Field(default_factory=list, max_length=40)


# ---------------------------------------------------------------------------
# Workflow 1: plan generation — input
# ---------------------------------------------------------------------------


class InterviewPlanWorkflowInput(StrictSchema):
    """Payload sent to the Dify interview plan workflow."""

    schema_version: str = "interview-plan-input-v1"
    user_locale: str = "zh-CN"
    interview_type: InterviewType
    resume: InterviewResumeInput
    job: InterviewJobInput
    match_report: InterviewMatchReportInput

    @model_validator(mode="after")
    def validate_schema_version(self) -> InterviewPlanWorkflowInput:
        if self.schema_version != "interview-plan-input-v1":
            raise ValueError("schema_version must be interview-plan-input-v1")
        return self


# ---------------------------------------------------------------------------
# Workflow 1: plan generation — output
# ---------------------------------------------------------------------------


class InterviewPlanQuestion(StrictSchema):
    """One question in the generated interview plan."""

    sequence: int = Field(ge=1, le=20)
    question_type: InterviewQuestionType
    prompt: str = Field(min_length=1, max_length=2000)
    intent: str = Field(default="", max_length=500)
    expected_evidence_keys: list[str] = Field(default_factory=list, max_length=20)


class InterviewPlanGeneration(StrictSchema):
    workflow_version: str = Field(min_length=1, max_length=120)
    workflow_run_id: str | None = Field(default=None, max_length=160)
    provider: str = Field(default="dify", max_length=80)
    latency_ms: int | None = Field(default=None, ge=0)


class InterviewPlanWorkflowOutput(StrictSchema):
    """Strict output contract returned by the Dify interview plan workflow."""

    schema_version: str = "interview-plan-v1"
    interview_type: InterviewType
    summary: str = Field(default="", max_length=1000)
    questions: list[InterviewPlanQuestion] = Field(min_length=3, max_length=8)
    missing_skill_warnings: list[str] = Field(default_factory=list, max_length=40)
    fabrication_warnings: list[str] = Field(default_factory=list, max_length=40)
    job_information_warning: str = Field(default="", max_length=2000)
    generation: InterviewPlanGeneration

    @model_validator(mode="after")
    def validate_schema_version(self) -> InterviewPlanWorkflowOutput:
        if self.schema_version != "interview-plan-v1":
            raise ValueError("schema_version must be interview-plan-v1")
        return self

    @model_validator(mode="after")
    def validate_question_sequences(self) -> InterviewPlanWorkflowOutput:
        sequences = [q.sequence for q in self.questions]
        if sequences != list(range(1, len(sequences) + 1)):
            raise ValueError("question sequences must be 1..N contiguous")
        return self


class InterviewPlanProviderAttempt(StrictSchema):
    """Masked metadata for one Dify workflow attempt inside the provider."""

    sequence: int = Field(ge=1)
    http_status: int | None = Field(default=None)
    workflow_run_id: str | None = Field(default=None, max_length=160)
    workflow_id: str | None = Field(default=None, max_length=160)
    status: str | None = Field(default=None, max_length=40)
    error: str | None = Field(default=None, max_length=240)
    total_steps: int | None = Field(default=None, ge=0)
    elapsed_time: float | None = Field(default=None, ge=0)
    outputs_keys: list[str] = Field(default_factory=list)
    error_code: str | None = Field(default=None, max_length=80)
    error_message: str | None = Field(default=None, max_length=240)
    latency_ms: int = Field(default=0, ge=0)
    retried: bool = False


class InterviewPlanProviderResult(StrictSchema):
    output: InterviewPlanWorkflowOutput
    raw_output: dict[str, JsonValue] = Field(default_factory=dict)
    attempts: list[InterviewPlanProviderAttempt] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# API schemas
# ---------------------------------------------------------------------------


class InterviewCreate(StrictSchema):
    resume_version_id: int = Field(ge=1)
    job_id: int = Field(ge=1)
    match_report_id: int = Field(ge=1)
    interview_type: InterviewType


class InterviewQuestionRead(StrictSchema):
    id: int
    session_id: int
    sequence: int
    question_type: InterviewQuestionType
    prompt: str
    intent: str = ""
    expected_evidence_keys: list[str] = Field(default_factory=list)
    created_at: datetime


class InterviewRead(StrictSchema):
    id: int
    user_id: int
    resume_version_id: int
    job_id: int
    interview_type: InterviewType
    status: InterviewStatus
    summary: str = ""
    missing_skill_warnings: list[str] = Field(default_factory=list)
    fabrication_warnings: list[str] = Field(default_factory=list)
    job_information_warning: str = ""
    workflow_run_id: str | None = None
    workflow_version: str | None = None
    provider: str | None = None
    latency_ms: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    questions: list[InterviewQuestionRead] = Field(default_factory=list)
    report: dict[str, JsonValue] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class InterviewListRead(StrictSchema):
    items: list[InterviewRead]
    total: int
    offset: int
    limit: int


# Chat-based interview schemas


class InterviewChatStatus(StrEnum):
    """State machine for the chat-based interview flow.

    * ``CREATED`` — session created, plan generated, chat not yet started.
    * ``GENERATING_PLAN`` — plan generation in progress.
    * ``WAITING_FOR_ANSWER`` — AI has asked a question, waiting for user.
    * ``PROCESSING_TURN`` — user answer submitted, Dify Chatflow running.
    * ``GENERATING_REPORT`` — interview ended, final evaluation in progress.
    * ``COMPLETED`` — final report generated.
    * ``CANCELLED`` — user manually cancelled.
    * ``FAILED`` — unrecoverable error.
    """

    CREATED = "CREATED"
    GENERATING_PLAN = "GENERATING_PLAN"
    WAITING_FOR_ANSWER = "WAITING_FOR_ANSWER"
    PROCESSING_TURN = "PROCESSING_TURN"
    GENERATING_REPORT = "GENERATING_REPORT"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class ChatNextAction(StrEnum):
    """The next action determined by the Chatflow after each turn."""

    FOLLOW_UP = "FOLLOW_UP"
    NEXT_QUESTION = "NEXT_QUESTION"
    COMPLETE_INTERVIEW = "COMPLETE_INTERVIEW"


# ---------------------------------------------------------------------------
# Chatflow: turn input / output (interview-chat-turn-v1)
# ---------------------------------------------------------------------------


class ChatTurnWorkflowInput(StrictSchema):
    """Payload sent to the Dify Interview Chat Chatflow for each turn.

    The ``user_answer`` field is empty on the first turn (the Chatflow
    generates the opening question). On subsequent turns it contains
    the user's answer to the current question or follow-up.
    """

    schema_version: str = "interview-chat-turn-input-v1"
    user_locale: str = "zh-CN"
    interview_type: InterviewType
    current_question_sequence: int = Field(ge=1, le=20)
    current_question_prompt: str = Field(min_length=1, max_length=2000)
    current_question_type: InterviewQuestionType
    current_question_intent: str = Field(default="", max_length=500)
    user_answer: str = Field(default="", max_length=8000)
    follow_up_count: int = Field(default=0, ge=0, le=10)
    total_questions: int = Field(default=4, ge=1, le=20)
    conversation_history: list[dict[str, JsonValue]] = Field(default_factory=list, max_length=200)
    resume: InterviewResumeInput
    job: InterviewJobInput
    match_report: InterviewMatchReportInput

    @model_validator(mode="after")
    def validate_schema_version(self) -> ChatTurnWorkflowInput:
        if self.schema_version != "interview-chat-turn-input-v1":
            raise ValueError("schema_version must be interview-chat-turn-input-v1")
        return self


class ChatTurnGeneration(StrictSchema):
    workflow_version: str = Field(min_length=1, max_length=120)
    workflow_run_id: str | None = Field(default=None, max_length=160)
    conversation_id: str | None = Field(default=None, max_length=160)
    provider: str = Field(default="dify", max_length=80)
    latency_ms: int | None = Field(default=None, ge=0)


class ChatTurnWorkflowOutput(StrictSchema):
    """Strict output contract returned by the Dify Interview Chat Chatflow."""

    schema_version: str = "interview-chat-turn-v1"
    assistant_message: str = Field(min_length=1, max_length=4000)
    next_action: ChatNextAction
    turn_analysis: str = Field(default="", max_length=4000)
    follow_up_reason: str = Field(default="", max_length=2000)
    unsupported_claims: list[str] = Field(default_factory=list, max_length=40)
    used_facts: list[str] = Field(default_factory=list, max_length=40)
    missing_skill_warnings: list[str] = Field(default_factory=list, max_length=40)
    fabrication_warnings: list[str] = Field(default_factory=list, max_length=40)
    generation: ChatTurnGeneration

    @model_validator(mode="after")
    def validate_schema_version(self) -> ChatTurnWorkflowOutput:
        if self.schema_version != "interview-chat-turn-v1":
            raise ValueError("schema_version must be interview-chat-turn-v1")
        return self


class ChatTurnProviderAttempt(StrictSchema):
    sequence: int = Field(ge=1)
    http_status: int | None = Field(default=None)
    workflow_run_id: str | None = Field(default=None, max_length=160)
    conversation_id: str | None = Field(default=None, max_length=160)
    status: str | None = Field(default=None, max_length=40)
    error: str | None = Field(default=None, max_length=240)
    total_steps: int | None = Field(default=None, ge=0)
    elapsed_time: float | None = Field(default=None, ge=0)
    outputs_keys: list[str] = Field(default_factory=list)
    error_code: str | None = Field(default=None, max_length=80)
    error_message: str | None = Field(default=None, max_length=240)
    latency_ms: int = Field(default=0, ge=0)
    retried: bool = False


class ChatTurnProviderResult(StrictSchema):
    output: ChatTurnWorkflowOutput
    raw_output: dict[str, JsonValue] = Field(default_factory=dict)
    conversation_id: str | None = Field(default=None, max_length=160)
    attempts: list[ChatTurnProviderAttempt] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Final Evaluation Workflow: input / output (interview-final-evaluation-v1)
# ---------------------------------------------------------------------------


class FinalEvaluationDimension(StrEnum):
    """The five scoring dimensions for the final evaluation report.

    Scores are integers 0-100. The ``overall_score`` is recomputed by
    Python as the arithmetic mean of the five dimension scores; the
    LLM-provided ``overall_score`` is never trusted directly.
    """

    RELEVANCE = "relevance"
    COMPLETENESS = "completeness"
    CLARITY = "clarity"
    STRUCTURE = "structure"
    TECHNICAL_ACCURACY = "technical_accuracy"


ALL_FINAL_DIMENSIONS: tuple[FinalEvaluationDimension, ...] = tuple(FinalEvaluationDimension)


class FinalDimensionScore(StrictSchema):
    """One dimension score in the final evaluation (0-100 integer)."""

    dimension: FinalEvaluationDimension
    score: int = Field(ge=0, le=100)
    rationale: str = Field(default="", max_length=1000)


class AnswerSequenceRef(StrictSchema):
    """Reference to a question sequence in best/weakest answer lists.

    ``question_sequence`` must map to a real question in the interview
    plan (1..N). The ``excerpt`` is a short quote from the user's answer.
    """

    question_sequence: int = Field(ge=1, le=20)
    excerpt: str = Field(default="", max_length=500)
    reason: str = Field(default="", max_length=1000)


class FinalEvaluationWorkflowInput(StrictSchema):
    """Payload sent to the Dify Interview Final Evaluation Workflow."""

    schema_version: str = "interview-final-evaluation-input-v1"
    user_locale: str = "zh-CN"
    interview_type: InterviewType
    transcript: list[dict[str, JsonValue]] = Field(min_length=1, max_length=500)
    question_count: int = Field(ge=1, le=20)
    resume: InterviewResumeInput
    job: InterviewJobInput
    match_report: InterviewMatchReportInput

    @model_validator(mode="after")
    def validate_schema_version(self) -> FinalEvaluationWorkflowInput:
        if self.schema_version != "interview-final-evaluation-input-v1":
            raise ValueError("schema_version must be interview-final-evaluation-input-v1")
        return self


class FinalEvaluationGeneration(StrictSchema):
    workflow_version: str = Field(min_length=1, max_length=120)
    workflow_run_id: str | None = Field(default=None, max_length=160)
    provider: str = Field(default="dify", max_length=80)
    latency_ms: int | None = Field(default=None, ge=0)


class FinalEvaluationWorkflowOutput(StrictSchema):
    """Strict output contract returned by the Dify Final Evaluation Workflow.

    The ``overall_score`` field from the LLM is **ignored** — Python
    recomputes it as the mean of the five ``dimension_scores``.
    """

    schema_version: str = "interview-final-evaluation-v1"
    dimension_scores: list[FinalDimensionScore] = Field(min_length=5, max_length=5)
    summary: str = Field(min_length=1, max_length=8000)
    strengths: list[str] = Field(default_factory=list, max_length=40)
    weaknesses: list[str] = Field(default_factory=list, max_length=40)
    best_answers: list[AnswerSequenceRef] = Field(default_factory=list, max_length=20)
    weakest_answers: list[AnswerSequenceRef] = Field(default_factory=list, max_length=20)
    unsupported_claims: list[str] = Field(default_factory=list, max_length=40)
    missing_skill_warnings: list[str] = Field(default_factory=list, max_length=40)
    fabrication_warnings: list[str] = Field(default_factory=list, max_length=40)
    improvement_suggestions: list[str] = Field(default_factory=list, max_length=40)
    practice_questions: list[str] = Field(default_factory=list, max_length=40)
    used_facts: list[str] = Field(default_factory=list, max_length=40)
    generation: FinalEvaluationGeneration

    @model_validator(mode="after")
    def validate_schema_version(self) -> FinalEvaluationWorkflowOutput:
        if self.schema_version != "interview-final-evaluation-v1":
            raise ValueError("schema_version must be interview-final-evaluation-v1")
        return self

    @model_validator(mode="after")
    def validate_dimensions_complete(self) -> FinalEvaluationWorkflowOutput:
        seen = {item.dimension for item in self.dimension_scores}
        required = set(ALL_FINAL_DIMENSIONS)
        if seen != required:
            missing = required - seen
            extra = seen - required
            parts: list[str] = []
            if missing:
                parts.append(f"missing: {sorted(m.value for m in missing)}")
            if extra:
                parts.append(f"extra: {sorted(e.value for e in extra)}")
            raise ValueError(f"dimension_scores must cover all 5 dimensions ({'; '.join(parts)})")
        return self


class FinalEvaluationProviderAttempt(StrictSchema):
    sequence: int = Field(ge=1)
    http_status: int | None = Field(default=None)
    workflow_run_id: str | None = Field(default=None, max_length=160)
    workflow_id: str | None = Field(default=None, max_length=160)
    status: str | None = Field(default=None, max_length=40)
    error: str | None = Field(default=None, max_length=240)
    total_steps: int | None = Field(default=None, ge=0)
    elapsed_time: float | None = Field(default=None, ge=0)
    outputs_keys: list[str] = Field(default_factory=list)
    error_code: str | None = Field(default=None, max_length=80)
    error_message: str | None = Field(default=None, max_length=240)
    latency_ms: int = Field(default=0, ge=0)
    retried: bool = False


class FinalEvaluationProviderResult(StrictSchema):
    output: FinalEvaluationWorkflowOutput
    raw_output: dict[str, JsonValue] = Field(default_factory=dict)
    attempts: list[FinalEvaluationProviderAttempt] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Chat API schemas
# ---------------------------------------------------------------------------


class InterviewMessageRead(StrictSchema):
    """One chat message in the interview conversation."""

    id: int
    session_id: int
    sequence: int
    role: str  # "USER" or "ASSISTANT"
    content: str
    created_at: datetime


class InterviewProgressRead(StrictSchema):
    """Current progress indicator for the chat-based interview."""

    current_question: int  # 1-based current question number
    total_questions: int
    follow_up_count: int


class InterviewMessageSubmit(StrictSchema):
    """User-submitted answer in the chat flow."""

    content: str = Field(min_length=1, max_length=8000)


class InterviewChatTurnResponse(StrictSchema):
    """Response for POST /api/interviews/{id}/messages."""

    user_message: InterviewMessageRead
    assistant_message: InterviewMessageRead
    next_action: str
    progress: InterviewProgressRead
    interview_completed: bool = False
    report_status: str = ""  # "pending", "generating", "ready", "failed"


class InterviewChatStatusRead(StrictSchema):
    """Response for start/complete/cancel endpoints."""

    id: int
    chat_status: InterviewChatStatus
    status: InterviewStatus
    progress: InterviewProgressRead
    dify_conversation_id: str | None = None


class FinalDimensionScoreRead(StrictSchema):
    dimension: FinalEvaluationDimension
    score: int
    rationale: str = ""


class AnswerSequenceRefRead(StrictSchema):
    question_sequence: int
    excerpt: str = ""
    reason: str = ""


class InterviewChatReportRead(StrictSchema):
    """Final report for the chat-based interview.

    All array fields default to empty lists so the frontend can safely
    access ``.length`` without ``undefined`` errors.
    """

    id: int
    status: InterviewStatus
    chat_status: str = ""
    interview_type: InterviewType
    overall_score: float | None
    dimension_scores: list[FinalDimensionScoreRead] = Field(default_factory=list)
    summary: str = ""
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    best_answers: list[AnswerSequenceRefRead] = Field(default_factory=list)
    weakest_answers: list[AnswerSequenceRefRead] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    missing_skill_warnings: list[str] = Field(default_factory=list)
    fabrication_warnings: list[str] = Field(default_factory=list)
    improvement_suggestions: list[str] = Field(default_factory=list)
    practice_questions: list[str] = Field(default_factory=list)
    used_facts: list[str] = Field(default_factory=list)
    question_count: int = 0
    answered_count: int = 0
    report: dict[str, JsonValue] = Field(default_factory=dict)
    generated_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
