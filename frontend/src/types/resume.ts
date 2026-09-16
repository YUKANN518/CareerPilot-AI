export type ResumeStatus =
  | "UPLOADED"
  | "EXTRACTING"
  | "EXTRACTED"
  | "PARSING"
  | "NEEDS_CONFIRMATION"
  | "CONFIRMED"
  | "FAILED"
  | "ARCHIVED"

export interface SourceLocation {
  source_type: "page" | "paragraph" | "table" | "unknown"
  page_number: number | null
  block_index: number | null
  paragraph_index: number | null
  table_index: number | null
  row_index: number | null
  label: string
}

export interface EvidenceField {
  value: string
  confidence: number
  evidence_text: string
  source_location: SourceLocation
  needs_confirmation: boolean
}

export interface StructuredSkill extends EvidenceField {
  category: string | null
  level: string | null
}

export interface BasicInfo {
  full_name: EvidenceField
  email: EvidenceField
  phone: EvidenceField
  location: EvidenceField
}

export interface EducationItem {
  institution: EvidenceField
  degree: EvidenceField
  field_of_study: EvidenceField
  start_date: EvidenceField
  end_date: EvidenceField
  description: EvidenceField
}

export interface WorkExperienceItem {
  company: EvidenceField
  title: EvidenceField
  start_date: EvidenceField
  end_date: EvidenceField
  description: EvidenceField
}

export interface ProjectExperienceItem {
  name: EvidenceField
  role: EvidenceField
  start_date: EvidenceField
  end_date: EvidenceField
  description: EvidenceField
}

export interface ResumeProfile {
  basic_info: BasicInfo
  education: EducationItem[]
  work_experience: WorkExperienceItem[]
  project_experience: ProjectExperienceItem[]
  technical_skills: StructuredSkill[]
  soft_skills: StructuredSkill[]
  languages: EvidenceField[]
  certificates: EvidenceField[]
  awards: EvidenceField[]
  summary: EvidenceField
}

export interface FileAsset {
  id: number
  original_name: string
  mime_type: string
  size_bytes: number
  sha256: string
  file_format: "pdf" | "docx"
}

export interface Resume {
  id: number
  title: string
  status: ResumeStatus
  file: FileAsset
  parse_attempts: number
  extracted_at: string | null
  parsed_at: string | null
  confirmed_at: string | null
  created_at: string
  updated_at: string
  version_count: number
  last_error_code: string | null
  last_error_message: string | null
}

export interface ResumeUploadResult {
  resume: Resume
  duplicate: boolean
}

export interface TextBlock {
  source_type: "page" | "paragraph" | "table"
  text: string
  page_number: number | null
  block_index: number | null
  paragraph_index: number | null
  table_index: number | null
  row_index: number | null
}

export interface ExtractionResult {
  resume_id: number
  status: ResumeStatus
  character_count: number
  blocks: TextBlock[]
}

export interface ParseResult {
  resume_id: number
  status: ResumeStatus
  result: ResumeProfile | null
  parse_attempts: number
  low_confidence_count: number
  error_code: string | null
  error_message: string | null
}

export interface ResumeVersion {
  id: number
  resume_id: number
  version_number: number
  structured_data: ResumeProfile
  is_current: boolean
  is_confirmed: boolean
  created_at: string
}

export interface ResumeSkill {
  id: number
  normalized_name: string
  raw_name: string
  category: string | null
  level: string | null
  confidence: number
  evidence_text: string
  evidence_section: string
  source_location: SourceLocation
  resume_version_id: number
  is_user_confirmed: boolean
}
