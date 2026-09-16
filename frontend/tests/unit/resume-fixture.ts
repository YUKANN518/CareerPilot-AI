import type { EvidenceField, ResumeProfile } from "@/types/resume"

export function evidence(
  value: string,
  confidence = 0.9,
  evidenceText = "Source evidence",
): EvidenceField {
  return {
    value,
    confidence,
    evidence_text: evidenceText,
    source_location: {
      source_type: "page",
      page_number: 1,
      block_index: 0,
      paragraph_index: null,
      table_index: null,
      row_index: null,
      label: "page:1:block:0",
    },
    needs_confirmation: confidence < 0.7,
  }
}

export function resumeProfile(): ResumeProfile {
  return {
    basic_info: {
      full_name: evidence("Sample Candidate", 0.5),
      email: evidence("sample@example.test"),
      phone: evidence("+86 138 0000 0000"),
      location: evidence("Shanghai"),
    },
    education: [],
    work_experience: [],
    project_experience: [],
    technical_skills: [
      {
        ...evidence("Python", 0.86, "Skills: Python and FastAPI."),
        category: "programming_language",
        level: null,
      },
    ],
    soft_skills: [],
    languages: [],
    certificates: [],
    awards: [],
    summary: evidence("Backend engineer."),
  }
}
