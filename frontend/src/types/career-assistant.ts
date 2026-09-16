export type CareerAssistantRunStatus =
  | "PENDING"
  | "RUNNING"
  | "SUCCEEDED"
  | "FAILED"
  | "CANCELLED"

export type CareerAssistantNodeStatus =
  | "PENDING"
  | "RUNNING"
  | "SUCCEEDED"
  | "FAILED"
  | "SKIPPED"
  | "CANCELLED"

export type CareerAssistantQAScope = "auto" | "knowledge" | "personal"

export type CareerAssistantQACitationSourceType =
  | "knowledge"
  | "resume"
  | "match_report"
  | "application"

export interface CareerAssistantQACitation {
  source_type: CareerAssistantQACitationSourceType
  source_id: number
  document_id: number
  title: string
  category: string
  chunk_index: number
  chunk_text: string
  quote: string
  page_number: number | null
  paragraph_index: number | null
  score: number
}

export interface CareerAssistantQA {
  id: number
  user_id: number
  question: string
  answer: string | null
  status: CareerAssistantRunStatus
  citations: CareerAssistantQACitation[]
  error_code: string | null
  error_message: string | null
  created_at: string
  finished_at: string | null
}

export interface CareerAssistantQAListItem {
  id: number
  question: string
  status: CareerAssistantRunStatus
  answer: string | null
  created_at: string
  finished_at: string | null
}

export interface CareerAssistantQAList {
  items: CareerAssistantQAListItem[]
  total: number
  offset: number
  limit: number
}

export interface CareerAssistantQACreateInput {
  question: string
  scope?: CareerAssistantQAScope
}

export interface CareerAssistantQAEventTicket {
  ticket: string
  expires_at: string
}

export interface CareerAssistantQAEvent {
  id: number
  event: string
  run_id: number
  node: string | null
  status: string
  timestamp: string
  duration_ms: number | null
  summary: Record<string, unknown>
  error_code: string | null
  error_message: string | null
  answer: string | null
  citations: Array<Record<string, unknown>>
}

export type KnowledgeDocumentStatus =
  | "PENDING"
  | "PROCESSING"
  | "READY"
  | "FAILED"

export interface KnowledgeDocument {
  id: number
  title: string
  category: string
  status: KnowledgeDocumentStatus
  chunk_count: number
  content_hash: string | null
  error_code: string | null
  error_message: string | null
  indexed_at: string | null
  created_at: string
  updated_at: string
}

export interface KnowledgeDocumentList {
  items: KnowledgeDocument[]
  total: number
  offset: number
  limit: number
}

export interface KnowledgeDocumentUploadInput {
  file: File
  title: string
  category: string
}

export interface KnowledgeDocumentReindexResult {
  document_id: number
  status: KnowledgeDocumentStatus
  chunk_count: number
  reused: boolean
}
