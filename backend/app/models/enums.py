from enum import StrEnum


class UserRole(StrEnum):
    USER = "USER"
    ADMIN = "ADMIN"


class ResumeStatus(StrEnum):
    UPLOADED = "UPLOADED"
    EXTRACTING = "EXTRACTING"
    EXTRACTED = "EXTRACTED"
    PARSING = "PARSING"
    NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"


class JobSourceType(StrEnum):
    MANUAL = "MANUAL"
    CSV = "CSV"
    GENERIC_HTML = "GENERIC_HTML"
    REST_API = "REST_API"
    SINGLE_JOB_URL = "SINGLE_JOB_URL"


class SourceStatus(StrEnum):
    DRAFT = "DRAFT"
    TESTED = "TESTED"
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"
    ERROR = "ERROR"


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    WAITING_REVIEW = "WAITING_REVIEW"


class RequirementStatus(StrEnum):
    SATISFIED = "SATISFIED"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"
    WARNING = "WARNING"


class ApplicationStatus(StrEnum):
    SAVED = "SAVED"
    APPLIED = "APPLIED"
    INTERVIEW = "INTERVIEW"
    OFFER = "OFFER"
    REJECTED = "REJECTED"
