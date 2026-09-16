from dataclasses import dataclass, field

from app.schemas.jobs import NormalizedJob

RawJob = dict[str, object]


@dataclass(frozen=True)
class AdapterTestResult:
    success: bool
    message: str
    latency_ms: int
    http_status: int | None = None


@dataclass
class AdapterPreview:
    jobs: list[NormalizedJob] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class SourceAdapterError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
