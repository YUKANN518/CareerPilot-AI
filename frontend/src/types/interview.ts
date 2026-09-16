export type InterviewType =
  | "COMPREHENSIVE"
  | "TECHNICAL"
  | "BEHAVIORAL"
  | "PROJECT"
  | "HR"

export type InterviewStatus =
  | "PLANNED"
  | "IN_PROGRESS"
  | "COMPLETED"
  | "REPORTED"
  | "FAILED"

export type InterviewChatStatus =
  | "CREATED"
  | "GENERATING_PLAN"
  | "WAITING_FOR_ANSWER"
  | "PROCESSING_TURN"
  | "GENERATING_REPORT"
  | "COMPLETED"
  | "CANCELLED"
  | "FAILED"

export type ChatNextAction = "FOLLOW_UP" | "NEXT_QUESTION" | "COMPLETE_INTERVIEW"

export type FinalEvaluationDimension =
  | "relevance"
  | "completeness"
  | "clarity"
  | "structure"
  | "technical_accuracy"

export type InterviewQuestionType =
  | "OPENING"
  | "TECHNICAL"
  | "BEHAVIORAL"
  | "PROJECT_DEEP_DIVE"
  | "SITUATIONAL"
  | "CLOSING"

export interface InterviewQuestion {
  id: number
  session_id: number
  sequence: number
  question_type: InterviewQuestionType
  prompt: string
  intent: string
  expected_evidence_keys: string[]
  created_at: string
}

export interface Interview {
  id: number
  user_id: number
  resume_version_id: number
  job_id: number
  interview_type: InterviewType
  status: InterviewStatus
  summary: string
  missing_skill_warnings: string[]
  fabrication_warnings: string[]
  job_information_warning: string
  workflow_run_id: string | null
  workflow_version: string | null
  provider: string | null
  latency_ms: number | null
  error_code: string | null
  error_message: string | null
  questions: InterviewQuestion[]
  report: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface InterviewList {
  items: Interview[]
  total: number
  offset: number
  limit: number
}

export interface InterviewCreateInput {
  resume_version_id: number
  job_id: number
  match_report_id: number
  interview_type: InterviewType
}

export interface InterviewMessage {
  id: number
  session_id: number
  sequence: number
  role: "USER" | "ASSISTANT"
  content: string
  created_at: string
}

export interface InterviewProgress {
  current_question: number
  total_questions: number
  follow_up_count: number
}

export interface InterviewChatStatusRead {
  id: number
  chat_status: InterviewChatStatus
  status: InterviewStatus
  progress: InterviewProgress
  dify_conversation_id: string | null
}

export interface InterviewMessageSubmit {
  content: string
}

export interface InterviewChatTurnResponse {
  user_message: InterviewMessage
  assistant_message: InterviewMessage
  next_action: ChatNextAction
  progress: InterviewProgress
  interview_completed: boolean
  report_status: string
}

export interface FinalDimensionScoreRead {
  dimension: FinalEvaluationDimension
  score: number
  rationale: string
}

export interface AnswerSequenceRefRead {
  question_sequence: number
  excerpt: string
  reason: string
}

export interface InterviewChatReportRead {
  id: number
  status: InterviewStatus
  chat_status: string
  interview_type: InterviewType
  overall_score: number | null
  dimension_scores: FinalDimensionScoreRead[]
  summary: string
  strengths: string[]
  weaknesses: string[]
  best_answers: AnswerSequenceRefRead[]
  weakest_answers: AnswerSequenceRefRead[]
  unsupported_claims: string[]
  missing_skill_warnings: string[]
  fabrication_warnings: string[]
  improvement_suggestions: string[]
  practice_questions: string[]
  used_facts: string[]
  question_count: number
  answered_count: number
  report: Record<string, unknown>
  generated_at: string | null
  error_code: string | null
  error_message: string | null
}
