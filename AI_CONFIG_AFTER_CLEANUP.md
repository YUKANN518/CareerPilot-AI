# CareerPilot AI configuration after Phase 1B

## Decision

Phase 1B reduced the Dify surface from eight feature keys to five. Configuration now follows
the focused product: evidence-grounded matching and career Q&A are first-class; Resume
Optimization and Chat Interview remain implemented but are hidden from the default navigation.

## Before cleanup

| Configuration | Former purpose | Decision |
| --- | --- | --- |
| `DIFY_LEARNING_PLAN_API_KEY` | Learning-plan generation | Removed with the feature |
| `DIFY_RESUME_OPTIMIZATION_API_KEY` | Grounded resume optimization | Retained; feature is hidden |
| `DIFY_KNOWLEDGE_QA_API_KEY` | Grounded Career Assistant | Retained; core feature |
| `DIFY_COVER_LETTER_API_KEY` | Cover-letter generation | Removed with the feature |
| `DIFY_INTERVIEW_PLAN_API_KEY` | Interview question planning | Retained; shared by Chat Interview |
| `DIFY_INTERVIEW_ANSWER_API_KEY` | Legacy one-shot answer scoring | Removed with the legacy flow |
| `DIFY_INTERVIEW_CHAT_API_KEY` | Conversational interview turns | Retained; feature is hidden |
| `DIFY_INTERVIEW_FINAL_API_KEY` | Conversational interview report | Retained; feature is hidden |

The corresponding removed workflow-version settings were deleted as well. Learning Plan did
not expose a separate workflow-version setting in the application configuration.

## After cleanup

The active Dify configuration is:

```env
DIFY_PROVIDER_MODE=fake
DIFY_BASE_URL=
DIFY_RESUME_OPTIMIZATION_API_KEY=
DIFY_RESUME_OPTIMIZATION_WORKFLOW_VERSION=resume-optimization-v1
DIFY_KNOWLEDGE_QA_API_KEY=
DIFY_KNOWLEDGE_QA_WORKFLOW_VERSION=knowledge-qa-v1
DIFY_INTERVIEW_PLAN_API_KEY=
DIFY_INTERVIEW_PLAN_WORKFLOW_VERSION=interview-plan-v1
DIFY_INTERVIEW_CHAT_API_KEY=
DIFY_INTERVIEW_CHAT_WORKFLOW_VERSION=interview-chat-turn-v1
DIFY_INTERVIEW_FINAL_API_KEY=
DIFY_INTERVIEW_FINAL_WORKFLOW_VERSION=interview-final-evaluation-v1
DIFY_TIMEOUT_SECONDS=60
```

## Why five settings remain

- Knowledge QA is the provider behind the main-navigation AI Assistant and must remain.
- Resume Optimization is evidence-grounded, uses a confirmed resume and successful match
  report, and is suitable for a future optional entry; it is hidden rather than deleted.
- Chat Interview still needs three distinct contracts: deterministic/remote question planning,
  conversational turns, and final transcript evaluation. The default local planner works
  without a plan key, but the key remains for optional real-provider use.
- `DIFY_PROVIDER_MODE=fake` remains the safe default. Real connectivity is not claimed by the
  offline test suite, and missing keys fail explicitly instead of silently presenting fake
  output as real.

The OpenAI-compatible settings remain unchanged because they power resume parsing, which is
part of the primary product journey.
