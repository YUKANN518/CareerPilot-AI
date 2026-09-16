"""Providers for the optional evidence-grounded chat interview.

The module supports deterministic/fake planning for local development and
Dify-backed plan, chat-turn, and final-evaluation workflows. Shared HTTP
helpers centralize retry, masking, and response parsing.
"""

from __future__ import annotations

import json
import time
from time import perf_counter
from typing import Any, Protocol

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.core.exceptions import AppError
from app.integrations.dify.workflow_helpers import (
    MAX_PROVIDER_RETRIES,
    RETRY_BACKOFF_SECONDS,
    _build_workflow_url,
    _elapsed_ms,
    _extract_masked_metadata,
    _extract_output,
    _is_retryable_error,
    _json_object,
    _string_path,
    _truncate,
)
from app.schemas.interviews import (
    AnswerSequenceRef,
    ChatNextAction,
    ChatTurnGeneration,
    ChatTurnProviderAttempt,
    ChatTurnProviderResult,
    ChatTurnWorkflowInput,
    ChatTurnWorkflowOutput,
    FinalDimensionScore,
    FinalEvaluationDimension,
    FinalEvaluationGeneration,
    FinalEvaluationProviderAttempt,
    FinalEvaluationProviderResult,
    FinalEvaluationWorkflowInput,
    FinalEvaluationWorkflowOutput,
    InterviewPlanGeneration,
    InterviewPlanProviderAttempt,
    InterviewPlanProviderResult,
    InterviewPlanQuestion,
    InterviewPlanWorkflowInput,
    InterviewPlanWorkflowOutput,
    InterviewQuestionType,
)

# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


class InterviewPlanProvider(Protocol):
    def generate_plan(
        self,
        request: InterviewPlanWorkflowInput,
    ) -> InterviewPlanProviderResult: ...



class InterviewChatProvider(Protocol):
    """Provider for the Dify Interview Chat Chatflow (Stage 7).

    Each call sends one turn (user answer or empty for the opening) and
    receives the AI interviewer's response plus a hidden ``next_action``
    decision. The ``conversation_id`` from the first response must be
    reused on all subsequent turns.
    """

    def chat_turn(
        self,
        request: ChatTurnWorkflowInput,
        *,
        conversation_id: str | None,
        user: str,
    ) -> ChatTurnProviderResult: ...


class InterviewFinalEvaluationProvider(Protocol):
    """Provider for the Dify Interview Final Evaluation Workflow (Stage 7).

    Called once after the interview completes to produce the consolidated
    report with five dimension scores (0-100). The ``overall_score`` is
    NOT included in the output - the service layer recomputes it from
    the dimension scores to avoid trusting the LLM.
    """

    def evaluate_final(
        self,
        request: FinalEvaluationWorkflowInput,
    ) -> FinalEvaluationProviderResult: ...


# ---------------------------------------------------------------------------
# Fake providers (deterministic, for tests and offline development)
# ---------------------------------------------------------------------------


class FakeInterviewPlanProvider:
    """Deterministic fake plan provider.

    Produces 4 questions that reference the user's real resume summary,
    matched skills and the job title. Never invents missing skills.
    """

    def generate_plan(
        self,
        request: InterviewPlanWorkflowInput,
    ) -> InterviewPlanProviderResult:
        matched_names = [
            str(item.get("normalized_name") or item.get("job_raw_name") or "")
            for item in request.match_report.matched_skills
            if item.get("normalized_name") or item.get("job_raw_name")
        ]
        missing_names = [
            str(item.get("normalized_name") or item.get("job_raw_name") or "")
            for item in request.match_report.missing_skills
            if item.get("normalized_name") or item.get("job_raw_name")
        ]

        resume = request.resume
        job = request.job
        summary_text = resume.summary or "experienced professional"
        skill_text = ", ".join(matched_names[:5]) if matched_names else "your core skills"

        questions: list[InterviewPlanQuestion] = [
            InterviewPlanQuestion(
                sequence=1,
                question_type=InterviewQuestionType.OPENING,
                prompt=(
                    f"请简单自我介绍，重点说明你为什么对 {job.title} 岗位感兴趣，"
                    f"以及你的背景如何与该岗位匹配。"
                ),
                intent="考察求职动机与自我认知",
                expected_evidence_keys=["resume_summary"],
            ),
            InterviewPlanQuestion(
                sequence=2,
                question_type=InterviewQuestionType.TECHNICAL,
                prompt=(
                    f"你在简历中提到熟练掌握 {skill_text}。请举一个具体项目"
                    f"例子，说明你如何运用这些技能解决实际问题。"
                ),
                intent="考察技术深度与项目经验真实性",
                expected_evidence_keys=["resume_skill", "resume_project"],
            ),
            InterviewPlanQuestion(
                sequence=3,
                question_type=InterviewQuestionType.PROJECT_DEEP_DIVE,
                prompt=(
                    "请详细介绍一个你简历中最具挑战性的项目，包括你的角色、"
                    "遇到的主要困难以及你是如何克服的。"
                ),
                intent="考察项目深度与问题解决能力",
                expected_evidence_keys=["resume_project", "resume_experience"],
            ),
            InterviewPlanQuestion(
                sequence=4,
                question_type=InterviewQuestionType.CLOSING,
                prompt=(
                    "如果你加入我们团队，你希望在未来 6 个月内实现什么目标？"
                    "你计划如何快速融入团队并开始贡献？"
                ),
                intent="考察职业规划与团队适配",
                expected_evidence_keys=[],
            ),
        ]

        missing_skill_warnings: list[str] = []
        if missing_names:
            missing_skill_warnings.append(
                "面试中不会询问缺失技能的深入问题: "
                + ", ".join(missing_names[:5])
                + ". 请在真实学习后再补充."
            )

        fabrication_warnings: list[str] = []
        job_warning = ""
        if job.is_summary_only:
            job_warning = "当前面试问题仅基于公开岗位摘要生成，不能覆盖原平台完整职位要求。"

        output = InterviewPlanWorkflowOutput(
            interview_type=request.interview_type,
            summary=(
                f"针对 {job.title} 岗位的 {request.interview_type.value} 面试，"
                f"基于简历背景: {summary_text[:100]}"
            ),
            questions=questions,
            missing_skill_warnings=missing_skill_warnings,
            fabrication_warnings=fabrication_warnings,
            job_information_warning=job_warning,
            generation=InterviewPlanGeneration(
                workflow_version="fake-interview-plan-v1",
                workflow_run_id=f"fake-plan-{request.match_report.report_id}",
                provider="fake",
                latency_ms=0,
            ),
        )
        return InterviewPlanProviderResult(
            output=output,
            raw_output=output.model_dump(mode="json"),
            attempts=[
                InterviewPlanProviderAttempt(
                    sequence=1,
                    http_status=200,
                    status="succeeded",
                    latency_ms=0,
                    retried=False,
                )
            ],
        )


class LocalInterviewPlanProvider:
    """Deterministic local interview plan provider (production default).

    Generates 4-8 hidden interview questions from the confirmed resume,
    target job, match report and interview type — without calling any
    external AI service. This is the default production provider because
    CareerPilot only retains two interview Dify apps (Chat Chatflow +
    Final Evaluation Workflow); plan generation is rule-based and local.

    Coverage by design:
      1. OPENING        — introduction / motivation
      2. TECHNICAL       — job-related technical (matched skills)
      3. PROJECT_DEEP_DIVE — resume project (only if projects exist)
      4. BEHAVIORAL      — behavioral / problem solving
      5. SITUATIONAL     — missing-skill improvement plan (only if missing)
      6. CLOSING         — situational or comprehensive

    Guarantees:
      * sequence is contiguous 1..N
      * no duplicate prompts
      * never references non-existent projects
      * never asks the user to demonstrate a missing skill as if mastered
      * does not modify the match score
    """

    _DEFAULT_QUESTION_COUNT = 5

    def generate_plan(
        self,
        request: InterviewPlanWorkflowInput,
    ) -> InterviewPlanProviderResult:
        resume = request.resume
        job = request.job
        report = request.match_report

        matched_names = self._skill_names(report.matched_skills)
        missing_names = self._skill_names(report.missing_skills)
        partial_names = self._skill_names(report.partial_skills)

        projects = self._extract_project_titles(resume.projects)
        summary_text = (resume.summary or "").strip() or "experienced professional"

        questions: list[InterviewPlanQuestion] = []
        seq = 1

        # 1. OPENING — introduction / motivation
        questions.append(
            InterviewPlanQuestion(
                sequence=seq,
                question_type=InterviewQuestionType.OPENING,
                prompt=(
                    f"请简单自我介绍，重点说明你为什么对 {job.title} 岗位感兴趣，"
                    f"以及你的背景如何与该岗位匹配。"
                ),
                intent="考察求职动机与自我认知",
                expected_evidence_keys=["resume_summary"],
            )
        )
        seq += 1

        # 2. TECHNICAL — job-related technical (matched skills only)
        skill_text = ", ".join(matched_names[:5]) if matched_names else "你的核心技能"
        questions.append(
            InterviewPlanQuestion(
                sequence=seq,
                question_type=InterviewQuestionType.TECHNICAL,
                prompt=(
                    f"你在简历中提到熟练掌握 {skill_text}。请举一个具体例子，"
                    f"说明你如何运用这些技能解决与 {job.title} 相关的实际问题。"
                ),
                intent="考察技术深度与岗位匹配度",
                expected_evidence_keys=["resume_skill", "resume_project"],
            )
        )
        seq += 1

        # 3. PROJECT_DEEP_DIVE — only if resume has real projects
        if projects:
            first_project = projects[0]
            questions.append(
                InterviewPlanQuestion(
                    sequence=seq,
                    question_type=InterviewQuestionType.PROJECT_DEEP_DIVE,
                    prompt=(
                        f"请详细介绍你的「{first_project}」项目，包括你的角色、"
                        f"遇到的主要技术困难以及你是如何克服的。"
                    ),
                    intent="考察项目深度与问题解决能力",
                    expected_evidence_keys=["resume_project"],
                )
            )
            seq += 1

        # 4. BEHAVIORAL — behavioral / problem solving
        questions.append(
            InterviewPlanQuestion(
                sequence=seq,
                question_type=InterviewQuestionType.BEHAVIORAL,
                prompt=(
                    "请描述一次你在团队中遇到意见分歧的经历。你是如何沟通并最终推动问题解决的？"
                ),
                intent="考察沟通协作与冲突处理能力",
                expected_evidence_keys=["resume_experience"],
            )
        )
        seq += 1

        # 5. SITUATIONAL — missing-skill improvement plan (only if missing skills exist)
        if missing_names:
            missing_text = ", ".join(missing_names[:3])
            questions.append(
                InterviewPlanQuestion(
                    sequence=seq,
                    question_type=InterviewQuestionType.SITUATIONAL,
                    prompt=(
                        f"匹配报告显示你目前尚未掌握 {missing_text}。"
                        f"请说明你的技能提升计划，以及你打算如何在短期内"
                        f"弥补这些技能差距以胜任 {job.title} 岗位。"
                    ),
                    intent="考察学习能力与自我认知（不要求已掌握）",
                    expected_evidence_keys=[],
                )
            )
            seq += 1

        # 6. CLOSING — situational or comprehensive
        questions.append(
            InterviewPlanQuestion(
                sequence=seq,
                question_type=InterviewQuestionType.CLOSING,
                prompt=(
                    f"如果你加入 {job.company} 担任 {job.title}，你希望在未来"
                    f" 6 个月内实现什么目标？你计划如何快速融入团队并开始贡献？"
                ),
                intent="考察职业规划与团队适配",
                expected_evidence_keys=[],
            )
        )

        # Build warnings
        missing_skill_warnings: list[str] = []
        if missing_names:
            missing_skill_warnings.append(
                "面试中不会询问缺失技能的深入技术问题: "
                + ", ".join(missing_names[:5])
                + "。相关问题仅询问提升计划，不会预设你已经掌握。"
            )

        fabrication_warnings: list[str] = []
        job_warning = ""
        if job.is_summary_only:
            job_warning = "当前面试问题仅基于公开岗位摘要生成，不能覆盖原平台完整职位要求。"
        if partial_names:
            fabrication_warnings.append(
                "部分匹配技能不会作为已掌握技能进行深入考察: " + ", ".join(partial_names[:5]) + "。"
            )

        summary = (
            f"针对 {job.company} 的 {job.title} 岗位的 "
            f"{request.interview_type.value} 面试，"
            f"基于简历背景: {summary_text[:100]}。"
            f"共生成 {len(questions)} 道问题。"
        )

        output = InterviewPlanWorkflowOutput(
            interview_type=request.interview_type,
            summary=summary,
            questions=questions,
            missing_skill_warnings=missing_skill_warnings,
            fabrication_warnings=fabrication_warnings,
            job_information_warning=job_warning,
            generation=InterviewPlanGeneration(
                workflow_version="local-interview-plan-v1",
                workflow_run_id=f"local-plan-{report.report_id}",
                provider="local",
                latency_ms=0,
            ),
        )
        return InterviewPlanProviderResult(
            output=output,
            raw_output=output.model_dump(mode="json"),
            attempts=[
                InterviewPlanProviderAttempt(
                    sequence=1,
                    http_status=200,
                    status="succeeded",
                    latency_ms=0,
                    retried=False,
                )
            ],
        )

    @staticmethod
    def _skill_names(items: list[dict[str, Any]]) -> list[str]:
        """Extract normalized skill names from match report skill items."""
        names: list[str] = []
        for item in items:
            name = str(item.get("normalized_name") or item.get("job_raw_name") or "").strip()
            if name:
                names.append(name)
        return names

    @staticmethod
    def _extract_project_titles(projects: list[dict[str, Any]]) -> list[str]:
        """Extract project titles from resume structured data.

        Only returns titles that actually exist in the resume — never
        fabricates project names. The resume structured_data stores
        fields as ``{"value": "...", "confidence": ...}`` dicts, so we
        unwrap the ``value`` key when present.
        """
        titles: list[str] = []
        for proj in projects:
            if not isinstance(proj, dict):
                continue
            raw_title = proj.get("title") or proj.get("name") or proj.get("project_name") or ""
            # The structured_data format wraps field values in
            # {"value": str, "confidence": float, ...} dicts.
            if isinstance(raw_title, dict):
                raw_title = raw_title.get("value") or ""
            title = str(raw_title).strip()
            if title:
                titles.append(title)
        return titles



class FakeInterviewChatProvider:
    """Deterministic fake chat provider for Stage 7 tests.

    The fake follows a simple deterministic policy:

    * **First turn** (``user_answer`` empty): emit the current question
      prompt as ``assistant_message`` and return ``NEXT_QUESTION`` (the
      service ignores ``next_action`` on the opening turn).
    * **Short answer + no follow-up yet**: emit a follow-up request and
      return ``FOLLOW_UP``.
    * **Adequate answer + more questions remain**: return
      ``NEXT_QUESTION``.
    * **Adequate answer + no questions remain**: return
      ``COMPLETE_INTERVIEW``.

    Fact-check: if the user's answer mentions any skill from
    ``missing_skills``, a ``fabrication_warning`` is emitted.
    """

    def chat_turn(
        self,
        request: ChatTurnWorkflowInput,
        *,
        conversation_id: str | None,
        user: str,
    ) -> ChatTurnProviderResult:
        is_first_turn = not request.user_answer.strip()
        new_conversation_id = conversation_id or f"fake-conv-{user}"

        missing_in_answer: list[str] = []
        for item in request.match_report.missing_skills:
            name = str(item.get("normalized_name") or "")
            if name and name.lower() in request.user_answer.lower():
                missing_in_answer.append(name)

        fabrication_warnings: list[str] = []
        if missing_in_answer:
            fabrication_warnings.append(
                "回答中提及了简历中未验证的技能: "
                + ", ".join(missing_in_answer[:5])
                + "。请谨慎评估。"
            )

        if is_first_turn:
            output = ChatTurnWorkflowOutput(
                assistant_message=request.current_question_prompt,
                next_action=ChatNextAction.NEXT_QUESTION,
                turn_analysis="",
                follow_up_reason="",
                unsupported_claims=[],
                used_facts=[],
                missing_skill_warnings=[
                    f"面试中不会询问缺失技能的深入问题: {name}" for name in missing_in_answer[:3]
                ],
                fabrication_warnings=[],
                generation=ChatTurnGeneration(
                    workflow_version="fake-interview-chat-turn-v1",
                    workflow_run_id=f"fake-chat-open-{request.current_question_sequence}",
                    conversation_id=new_conversation_id,
                    provider="fake",
                    latency_ms=0,
                ),
            )
            return ChatTurnProviderResult(
                output=output,
                raw_output=output.model_dump(mode="json"),
                conversation_id=new_conversation_id,
                attempts=[
                    ChatTurnProviderAttempt(
                        sequence=1,
                        http_status=200,
                        status="succeeded",
                        conversation_id=new_conversation_id,
                        latency_ms=0,
                        retried=False,
                    )
                ],
            )

        answer_len = len(request.user_answer.strip())

        if answer_len < 50 and request.follow_up_count < 1:
            next_action = ChatNextAction.FOLLOW_UP
            assistant_message = "你的回答比较简短，能否结合具体的项目经验或数据再详细说明一下？"
            follow_up_reason = "回答过于简短，需要更多细节来评估"
        elif request.current_question_sequence < request.total_questions:
            next_action = ChatNextAction.NEXT_QUESTION
            assistant_message = "好的，回答得不错。我们进入下一个问题。"
            follow_up_reason = ""
        else:
            next_action = ChatNextAction.COMPLETE_INTERVIEW
            assistant_message = (
                "感谢你的回答。本次模拟面试已经结束，我会为你生成一份详细的评估报告。"
            )
            follow_up_reason = ""

        matched_in_answer: list[str] = []
        for item in request.match_report.matched_skills:
            name = str(item.get("normalized_name") or "")
            if name and name.lower() in request.user_answer.lower():
                matched_in_answer.append(name)

        used_facts: list[str] = []
        if matched_in_answer:
            used_facts.append(f"回答引用了简历中已验证的技能: {', '.join(matched_in_answer[:5])}")

        missing_skill_warnings: list[str] = []
        if missing_in_answer:
            missing_skill_warnings.append(
                "回答中提及了缺失技能，AI 评分不反映对该技能的真实掌握程度。"
            )

        output = ChatTurnWorkflowOutput(
            assistant_message=assistant_message,
            next_action=next_action,
            turn_analysis=f"回答长度 {answer_len} 字符，"
            f"当前题号 {request.current_question_sequence}/{request.total_questions}，"
            f"追问次数 {request.follow_up_count}。",
            follow_up_reason=follow_up_reason,
            unsupported_claims=missing_in_answer[:5],
            used_facts=used_facts,
            missing_skill_warnings=missing_skill_warnings,
            fabrication_warnings=fabrication_warnings,
            generation=ChatTurnGeneration(
                workflow_version="fake-interview-chat-turn-v1",
                workflow_run_id=(
                    f"fake-chat-{request.current_question_sequence}-{request.follow_up_count + 1}"
                ),
                conversation_id=new_conversation_id,
                provider="fake",
                latency_ms=0,
            ),
        )
        return ChatTurnProviderResult(
            output=output,
            raw_output=output.model_dump(mode="json"),
            conversation_id=new_conversation_id,
            attempts=[
                ChatTurnProviderAttempt(
                    sequence=1,
                    http_status=200,
                    status="succeeded",
                    conversation_id=new_conversation_id,
                    latency_ms=0,
                    retried=False,
                )
            ],
        )


class FakeInterviewFinalEvaluationProvider:
    """Deterministic fake final evaluation provider for Stage 7 tests.

    Produces five dimension scores (0-100) based on transcript length.
    The ``overall_score`` is NOT included - the service computes it as
    the mean of the five dimensions.

    ``best_answers`` and ``weakest_answers`` only reference sequences
    1..``question_count`` to satisfy the "real question_sequence" rule.
    """

    def evaluate_final(
        self,
        request: FinalEvaluationWorkflowInput,
    ) -> FinalEvaluationProviderResult:
        total_chars = sum(
            len(str(m.get("content", ""))) for m in request.transcript if m.get("role") == "USER"
        )
        base_score = min(88, max(45, total_chars // 100 + 45))

        missing_in_transcript: list[str] = []
        for item in request.match_report.missing_skills:
            name = str(item.get("normalized_name") or "")
            if name and any(
                name.lower() in str(m.get("content", "")).lower()
                for m in request.transcript
                if m.get("role") == "USER"
            ):
                missing_in_transcript.append(name)

        fabrication_warnings: list[str] = []
        if missing_in_transcript:
            fabrication_warnings.append(
                "面试中提及了简历中未验证的技能: "
                + ", ".join(missing_in_transcript[:5])
                + "。评估报告已标注该风险。"
            )

        dimension_scores: list[FinalDimensionScore] = [
            FinalDimensionScore(
                dimension=FinalEvaluationDimension.RELEVANCE,
                score=base_score,
                rationale="回答与问题的相关性评估（AI 评价）",
            ),
            FinalDimensionScore(
                dimension=FinalEvaluationDimension.COMPLETENESS,
                score=max(0, base_score - 5),
                rationale="回答完整度评估（AI 评价）",
            ),
            FinalDimensionScore(
                dimension=FinalEvaluationDimension.CLARITY,
                score=min(100, base_score + 2),
                rationale="回答清晰度评估（AI 评价）",
            ),
            FinalDimensionScore(
                dimension=FinalEvaluationDimension.STRUCTURE,
                score=max(0, base_score - 10),
                rationale="回答结构评估（AI 评价，如 STAR 法则）",
            ),
            FinalDimensionScore(
                dimension=FinalEvaluationDimension.TECHNICAL_ACCURACY,
                score=max(0, base_score - 3),
                rationale="技术准确性评估（AI 评价）",
            ),
        ]

        max_seq = request.question_count
        best_seq = 1
        weakest_seq = min(2, max_seq) if max_seq >= 2 else 1

        output = FinalEvaluationWorkflowOutput(
            dimension_scores=dimension_scores,
            summary=(
                f"本次模拟面试共 {request.question_count} 个问题。"
                f"候选人总体表现{'良好' if base_score >= 70 else '一般'}，"
                f"建议在回答结构和量化成果方面进一步提升。"
            ),
            strengths=[
                "回答与岗位要求的相关性较高",
                "能够引用部分项目经验",
            ],
            weaknesses=[
                "回答结构有待改善，建议使用 STAR 法则",
                "部分回答缺少量化数据",
            ],
            best_answers=[
                AnswerSequenceRef(
                    question_sequence=best_seq,
                    excerpt="（最佳回答摘录）",
                    reason="回答结构清晰，引用了具体项目",
                )
            ],
            weakest_answers=[
                AnswerSequenceRef(
                    question_sequence=weakest_seq,
                    excerpt="（待改进回答摘录）",
                    reason="回答过于简短，缺少细节",
                )
            ],
            unsupported_claims=missing_in_transcript[:5],
            missing_skill_warnings=[
                f"面试中提及了缺失技能: {name}" for name in missing_in_transcript[:3]
            ]
            if missing_in_transcript
            else [],
            fabrication_warnings=fabrication_warnings,
            improvement_suggestions=[
                "使用 STAR 法则组织回答",
                "增加量化数据和具体成果",
                "提前准备项目深挖问题的细节",
            ],
            practice_questions=[
                "请描述一个你遇到的技术难题及解决过程",
                "请举例说明你如何在团队中推动一项变革",
            ],
            used_facts=[
                "基于简历中已验证的技能和项目经验进行评估",
            ],
            generation=FinalEvaluationGeneration(
                workflow_version="fake-interview-final-evaluation-v1",
                workflow_run_id=f"fake-final-{request.question_count}",
                provider="fake",
                latency_ms=0,
            ),
        )
        return FinalEvaluationProviderResult(
            output=output,
            raw_output=output.model_dump(mode="json"),
            attempts=[
                FinalEvaluationProviderAttempt(
                    sequence=1,
                    http_status=200,
                    status="succeeded",
                    latency_ms=0,
                    retried=False,
                )
            ],
        )


# ---------------------------------------------------------------------------
# Real Dify providers
# ---------------------------------------------------------------------------


def _post_to_dify(
    *,
    url: str,
    api_key: str,
    payload: dict[str, Any],
    timeout_seconds: float,
    workflow_version: str,
) -> tuple[dict[str, Any], int]:
    """Shared HTTP POST helper used by both real Dify providers.

    Returns (raw_json, http_status). Raises AppError on failure.
    """
    try:
        with httpx.Client(
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = client.post(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
    except httpx.TimeoutException as exc:
        raise AppError("DIFY_TIMEOUT", "Dify interview request timed out", 504) from exc
    except httpx.HTTPError as exc:
        raise AppError(
            "DIFY_UNAVAILABLE",
            "Dify interview provider is unavailable",
            503,
        ) from exc

    from app.integrations.dify.workflow_helpers import RETRYABLE_HTTP_STATUS

    if response.status_code in RETRYABLE_HTTP_STATUS:
        raise AppError(
            "DIFY_HTTP_RETRYABLE",
            f"Dify returned retryable HTTP status {response.status_code}",
            502,
        )
    if response.status_code >= 400:
        raise AppError(
            "DIFY_REQUEST_FAILED",
            "Dify interview request failed",
            502,
        )
    try:
        raw = response.json()
    except (json.JSONDecodeError, ValueError) as exc:
        raise AppError(
            "DIFY_OUTPUT_INVALID",
            "Dify returned a non-JSON response",
            502,
        ) from exc
    return raw, response.status_code


class DifyInterviewPlanProvider:
    """Real Dify provider for interview plan generation.

    This is an optional compatibility provider. The default production
    path uses ``LocalInterviewPlanProvider`` because CareerPilot only
    retains two interview Dify apps (Chat Chatflow + Final Evaluation
    Workflow); plan generation is deterministic and local.
    """

    def __init__(self, settings: Settings) -> None:
        if not settings.dify_base_url or not settings.dify_interview_plan_api_key:
            raise AppError(
                "DIFY_NOT_CONFIGURED",
                "Dify interview plan provider is not configured",
                503,
            )
        self.base_url = settings.dify_base_url.rstrip("/")
        self.api_key = settings.dify_interview_plan_api_key
        self.timeout_seconds = settings.dify_timeout_seconds
        self.workflow_version = settings.dify_interview_plan_workflow_version
        self.workflow_url = _build_workflow_url(self.base_url)

    def generate_plan(
        self,
        request: InterviewPlanWorkflowInput,
    ) -> InterviewPlanProviderResult:
        started = perf_counter()
        payload = {
            "inputs": {
                "data": json.dumps(request.model_dump(mode="json"), ensure_ascii=False),
            },
            "response_mode": "blocking",
            "user": f"careerpilot-user-{request.resume.resume_version_id}",
        }
        attempts: list[InterviewPlanProviderAttempt] = []
        last_error: AppError | None = None
        for attempt_index in range(MAX_PROVIDER_RETRIES + 1):
            attempt_started = perf_counter()
            retried = attempt_index > 0
            if retried:
                backoff = RETRY_BACKOFF_SECONDS[attempt_index - 1]
                time.sleep(backoff)
            try:
                raw, http_status = _post_to_dify(
                    url=self.workflow_url,
                    api_key=self.api_key,
                    payload=payload,
                    timeout_seconds=self.timeout_seconds,
                    workflow_version=self.workflow_version,
                )
            except AppError as exc:
                attempt_latency = _elapsed_ms(attempt_started)
                attempts.append(
                    InterviewPlanProviderAttempt(
                        sequence=attempt_index + 1,
                        http_status=None,
                        latency_ms=attempt_latency,
                        retried=retried,
                        error_code=exc.code,
                        error_message=_truncate(exc.message, 240),
                    )
                )
                last_error = exc
                if not _is_retryable_error(exc):
                    break
                continue

            attempt_metadata = _extract_masked_metadata(raw, http_status)
            attempt_latency = _elapsed_ms(attempt_started)
            try:
                output_payload = _extract_output(raw)
                output = InterviewPlanWorkflowOutput.model_validate(output_payload)
            except AppError as exc:
                attempts.append(
                    InterviewPlanProviderAttempt(
                        sequence=attempt_index + 1,
                        latency_ms=attempt_latency,
                        retried=retried,
                        error_code=exc.code,
                        error_message=_truncate(exc.message, 240),
                        **attempt_metadata,
                    )
                )
                last_error = exc
                if not _is_retryable_error(exc):
                    break
                continue
            except ValidationError:
                attempts.append(
                    InterviewPlanProviderAttempt(
                        sequence=attempt_index + 1,
                        latency_ms=attempt_latency,
                        retried=retried,
                        error_code="DIFY_OUTPUT_INVALID",
                        error_message=_truncate("Dify output failed Pydantic validation", 240),
                        **attempt_metadata,
                    )
                )
                last_error = AppError(
                    "DIFY_OUTPUT_INVALID",
                    "Dify output failed Pydantic validation",
                    502,
                )
                break

            workflow_run_id = _string_path(raw, ("workflow_run_id",)) or _string_path(
                raw, ("data", "workflow_run_id")
            )
            latency_ms = max(_elapsed_ms(started), 0)
            output = output.model_copy(
                update={
                    "generation": output.generation.model_copy(
                        update={
                            "workflow_run_id": output.generation.workflow_run_id or workflow_run_id,
                            "workflow_version": output.generation.workflow_version
                            or self.workflow_version,
                            "provider": "dify",
                            "latency_ms": output.generation.latency_ms or latency_ms,
                        }
                    )
                }
            )
            attempts.append(
                InterviewPlanProviderAttempt(
                    sequence=attempt_index + 1,
                    latency_ms=attempt_latency,
                    retried=retried,
                    **attempt_metadata,
                )
            )
            return InterviewPlanProviderResult(
                output=output,
                raw_output=_json_object(raw),
                attempts=attempts,
            )

        assert last_error is not None
        raise last_error



def _build_chat_messages_url(base_url: str) -> str:
    """Construct the Dify chat-messages URL, tolerating base URLs with or without /v1."""
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        return f"{normalized}/chat-messages"
    return f"{normalized}/v1/chat-messages"


def _extract_chat_output(raw: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Extract the parsed output dict and conversation_id from a chat response.

    Dify ``POST /v1/chat-messages`` returns ``conversation_id`` and
    ``answer`` (a string). The Chatflow is expected to emit a JSON
    string in ``answer`` containing the ``ChatTurnWorkflowOutput`` fields.

    Returns ``(parsed_dict, conversation_id)``. Raises ``AppError`` on
    missing conversation_id, empty answer, invalid JSON, or non-object JSON.
    """
    conversation_id = raw.get("conversation_id")
    if not isinstance(conversation_id, str) or not conversation_id.strip():
        raise AppError(
            "DIFY_EMPTY_OUTPUT",
            "Dify chat response missing conversation_id",
            502,
        )

    answer = raw.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        raise AppError(
            "DIFY_EMPTY_RESULT",
            "Dify chat response has empty answer",
            502,
        )

    try:
        parsed = json.loads(answer)
    except json.JSONDecodeError as exc:
        raise AppError(
            "DIFY_INVALID_JSON",
            "Dify chat answer is not valid JSON",
            502,
        ) from exc

    if not isinstance(parsed, dict):
        raise AppError(
            "DIFY_OUTPUT_INVALID",
            "Dify chat answer is not a JSON object",
            502,
        )

    return parsed, conversation_id


def _extract_chat_masked_metadata(
    raw: dict[str, Any],
    http_status: int,
) -> dict[str, Any]:
    """Build masked metadata for a chat response (no sensitive data).

    The returned dict is spread into ``ChatTurnProviderAttempt`` via
    ``**metadata``. It must only contain keys that exist on that schema
    (``workflow_id`` is intentionally absent — chat responses identify
    runs by ``message_id`` mapped to ``workflow_run_id``, and
    ``ChatTurnProviderAttempt`` has no ``workflow_id`` field).
    """
    return {
        "http_status": http_status,
        "workflow_run_id": _truncate_str(raw.get("message_id")),
        "conversation_id": _truncate_str(raw.get("conversation_id")),
        "status": "succeeded" if http_status == 200 else None,
        "error": None,
        "total_steps": None,
        "elapsed_time": None,
        "outputs_keys": sorted(raw.keys()) if isinstance(raw, dict) else [],
    }


def _truncate_str(value: Any, max_length: int = 160) -> str | None:
    if not isinstance(value, str):
        return None
    if len(value) <= max_length:
        return value
    return value[: max_length - 3] + "..."


class DifyInterviewChatProvider:
    """Real Dify provider for the Interview Chat Chatflow.

    Uses ``POST /v1/chat-messages`` with blocking mode. The first turn
    sends an empty ``conversation_id``; subsequent turns reuse the one
    returned by the first response. The ``user`` field is stable per
    session so Dify can track the conversation.
    """

    def __init__(self, settings: Settings) -> None:
        if not settings.dify_base_url or not settings.dify_interview_chat_api_key:
            raise AppError(
                "DIFY_NOT_CONFIGURED",
                "Dify interview chat provider is not configured",
                503,
            )
        self.base_url = settings.dify_base_url.rstrip("/")
        self.api_key = settings.dify_interview_chat_api_key
        self.timeout_seconds = settings.dify_timeout_seconds
        self.workflow_version = settings.dify_interview_chat_workflow_version
        self.chat_url = _build_chat_messages_url(self.base_url)

    def chat_turn(
        self,
        request: ChatTurnWorkflowInput,
        *,
        conversation_id: str | None,
        user: str,
    ) -> ChatTurnProviderResult:
        started = perf_counter()
        payload = {
            "inputs": {
                "data": json.dumps(request.model_dump(mode="json"), ensure_ascii=False),
            },
            "query": request.user_answer or " ",
            "response_mode": "blocking",
            "conversation_id": conversation_id or "",
            "user": user,
        }
        attempts: list[ChatTurnProviderAttempt] = []
        last_error: AppError | None = None
        for attempt_index in range(MAX_PROVIDER_RETRIES + 1):
            attempt_started = perf_counter()
            retried = attempt_index > 0
            if retried:
                backoff = RETRY_BACKOFF_SECONDS[attempt_index - 1]
                time.sleep(backoff)
            try:
                raw, http_status = _post_to_dify(
                    url=self.chat_url,
                    api_key=self.api_key,
                    payload=payload,
                    timeout_seconds=self.timeout_seconds,
                    workflow_version=self.workflow_version,
                )
            except AppError as exc:
                attempt_latency = _elapsed_ms(attempt_started)
                attempts.append(
                    ChatTurnProviderAttempt(
                        sequence=attempt_index + 1,
                        http_status=None,
                        latency_ms=attempt_latency,
                        retried=retried,
                        error_code=exc.code,
                        error_message=_truncate(exc.message, 240),
                    )
                )
                last_error = exc
                if not _is_retryable_error(exc):
                    break
                continue

            attempt_metadata = _extract_chat_masked_metadata(raw, http_status)
            attempt_latency = _elapsed_ms(attempt_started)
            try:
                output_payload, returned_conversation_id = _extract_chat_output(raw)
                output = ChatTurnWorkflowOutput.model_validate(output_payload)
            except AppError as exc:
                attempts.append(
                    ChatTurnProviderAttempt(
                        sequence=attempt_index + 1,
                        latency_ms=attempt_latency,
                        retried=retried,
                        error_code=exc.code,
                        error_message=_truncate(exc.message, 240),
                        **attempt_metadata,
                    )
                )
                last_error = exc
                if not _is_retryable_error(exc):
                    break
                continue
            except ValidationError:
                attempts.append(
                    ChatTurnProviderAttempt(
                        sequence=attempt_index + 1,
                        latency_ms=attempt_latency,
                        retried=retried,
                        error_code="DIFY_OUTPUT_INVALID",
                        error_message=_truncate("Dify chat output failed Pydantic validation", 240),
                        **attempt_metadata,
                    )
                )
                last_error = AppError(
                    "DIFY_OUTPUT_INVALID",
                    "Dify chat output failed Pydantic validation",
                    502,
                )
                break

            message_id = _string_path(raw, ("message_id",))
            latency_ms = max(_elapsed_ms(started), 0)
            output = output.model_copy(
                update={
                    "generation": output.generation.model_copy(
                        update={
                            "workflow_run_id": output.generation.workflow_run_id or message_id,
                            "workflow_version": output.generation.workflow_version
                            or self.workflow_version,
                            "conversation_id": output.generation.conversation_id
                            or returned_conversation_id,
                            "provider": "dify",
                            "latency_ms": output.generation.latency_ms or latency_ms,
                        }
                    )
                }
            )
            attempts.append(
                ChatTurnProviderAttempt(
                    sequence=attempt_index + 1,
                    latency_ms=attempt_latency,
                    retried=retried,
                    **attempt_metadata,
                )
            )
            return ChatTurnProviderResult(
                output=output,
                raw_output=_json_object(raw),
                conversation_id=returned_conversation_id,
                attempts=attempts,
            )

        assert last_error is not None
        raise last_error


# ---------------------------------------------------------------------------
# Real Dify final evaluation provider (POST /v1/workflows/run)
# ---------------------------------------------------------------------------


class DifyInterviewFinalEvaluationProvider:
    """Real Dify provider for the Interview Final Evaluation Workflow.

    Uses ``POST /v1/workflows/run`` in blocking mode, same as the
    existing plan/answer providers. The output does NOT include
    ``overall_score`` — the service layer recomputes it from the five
    dimension scores.
    """

    def __init__(self, settings: Settings) -> None:
        if not settings.dify_base_url or not settings.dify_interview_final_api_key:
            raise AppError(
                "DIFY_NOT_CONFIGURED",
                "Dify interview final evaluation provider is not configured",
                503,
            )
        self.base_url = settings.dify_base_url.rstrip("/")
        self.api_key = settings.dify_interview_final_api_key
        self.timeout_seconds = settings.dify_timeout_seconds
        self.workflow_version = settings.dify_interview_final_workflow_version
        self.workflow_url = _build_workflow_url(self.base_url)

    def evaluate_final(
        self,
        request: FinalEvaluationWorkflowInput,
    ) -> FinalEvaluationProviderResult:
        started = perf_counter()
        payload = {
            "inputs": {
                "data": json.dumps(request.model_dump(mode="json"), ensure_ascii=False),
            },
            "response_mode": "blocking",
            "user": f"careerpilot-interview-final-{request.question_count}",
        }
        attempts: list[FinalEvaluationProviderAttempt] = []
        last_error: AppError | None = None
        for attempt_index in range(MAX_PROVIDER_RETRIES + 1):
            attempt_started = perf_counter()
            retried = attempt_index > 0
            if retried:
                backoff = RETRY_BACKOFF_SECONDS[attempt_index - 1]
                time.sleep(backoff)
            try:
                raw, http_status = _post_to_dify(
                    url=self.workflow_url,
                    api_key=self.api_key,
                    payload=payload,
                    timeout_seconds=self.timeout_seconds,
                    workflow_version=self.workflow_version,
                )
            except AppError as exc:
                attempt_latency = _elapsed_ms(attempt_started)
                attempts.append(
                    FinalEvaluationProviderAttempt(
                        sequence=attempt_index + 1,
                        http_status=None,
                        latency_ms=attempt_latency,
                        retried=retried,
                        error_code=exc.code,
                        error_message=_truncate(exc.message, 240),
                    )
                )
                last_error = exc
                if not _is_retryable_error(exc):
                    break
                continue

            attempt_metadata = _extract_masked_metadata(raw, http_status)
            attempt_latency = _elapsed_ms(attempt_started)
            try:
                output_payload = _extract_output(raw)
                output = FinalEvaluationWorkflowOutput.model_validate(output_payload)
            except AppError as exc:
                attempts.append(
                    FinalEvaluationProviderAttempt(
                        sequence=attempt_index + 1,
                        latency_ms=attempt_latency,
                        retried=retried,
                        error_code=exc.code,
                        error_message=_truncate(exc.message, 240),
                        **attempt_metadata,
                    )
                )
                last_error = exc
                if not _is_retryable_error(exc):
                    break
                continue
            except ValidationError:
                attempts.append(
                    FinalEvaluationProviderAttempt(
                        sequence=attempt_index + 1,
                        latency_ms=attempt_latency,
                        retried=retried,
                        error_code="DIFY_OUTPUT_INVALID",
                        error_message=_truncate("Dify output failed Pydantic validation", 240),
                        **attempt_metadata,
                    )
                )
                last_error = AppError(
                    "DIFY_OUTPUT_INVALID",
                    "Dify output failed Pydantic validation",
                    502,
                )
                break

            workflow_run_id = _string_path(raw, ("workflow_run_id",)) or _string_path(
                raw, ("data", "workflow_run_id")
            )
            latency_ms = max(_elapsed_ms(started), 0)
            output = output.model_copy(
                update={
                    "generation": output.generation.model_copy(
                        update={
                            "workflow_run_id": output.generation.workflow_run_id or workflow_run_id,
                            "workflow_version": output.generation.workflow_version
                            or self.workflow_version,
                            "provider": "dify",
                            "latency_ms": output.generation.latency_ms or latency_ms,
                        }
                    )
                }
            )
            attempts.append(
                FinalEvaluationProviderAttempt(
                    sequence=attempt_index + 1,
                    latency_ms=attempt_latency,
                    retried=retried,
                    **attempt_metadata,
                )
            )
            return FinalEvaluationProviderResult(
                output=output,
                raw_output=_json_object(raw),
                attempts=attempts,
            )

        assert last_error is not None
        raise last_error


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def create_interview_plan_provider(settings: Settings) -> InterviewPlanProvider:
    """Build the interview plan provider.

    Provider selection:
      * ``dify`` mode + plan key → ``DifyInterviewPlanProvider``.
      * ``dify`` mode without plan key → deterministic local planning.
      * ``fake`` mode → ``FakeInterviewPlanProvider`` (tests only).
    """
    if settings.dify_provider_mode == "dify":
        if settings.dify_interview_plan_api_key:
            return DifyInterviewPlanProvider(settings)
        return LocalInterviewPlanProvider()
    return FakeInterviewPlanProvider()



def create_interview_chat_provider(settings: Settings) -> InterviewChatProvider:
    if settings.dify_provider_mode == "dify":
        return DifyInterviewChatProvider(settings)
    return FakeInterviewChatProvider()


def create_interview_final_evaluation_provider(
    settings: Settings,
) -> InterviewFinalEvaluationProvider:
    if settings.dify_provider_mode == "dify":
        return DifyInterviewFinalEvaluationProvider(settings)
    return FakeInterviewFinalEvaluationProvider()
