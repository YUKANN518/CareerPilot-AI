from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "development"
    app_name: str = "CareerPilot AI"
    api_v1_prefix: str = "/api"
    database_url: str = "sqlite:///../data/careerpilot.db"
    jwt_secret_key: str = "change-this-development-key-before-production"
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    login_rate_limit_attempts: int = 5
    login_rate_limit_window_seconds: int = 300
    login_rate_limit_lock_seconds: int = 900
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:4173"
    auto_create_tables: bool = True
    demo_admin_enabled: bool = True
    demo_admin_email: str = "admin@careerpilot.local"
    demo_admin_password: str = "Admin123456!"
    upload_directory: str = "../data/uploads"
    resume_max_upload_mb: int = 10
    resume_low_confidence_threshold: float = 0.7
    resume_parse_retries: int = 2
    ai_provider: Literal["mock", "openai_compatible"] = "mock"
    openai_base_url: str = "https://api.deepseek.com"
    openai_api_key: str | None = None
    openai_chat_model: str = "deepseek-v4-flash"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_temperature: float = 0.0
    openai_timeout_seconds: float = 30.0
    openai_http_retries: int = 2
    # The real-provider validation runner is always opt-in and never enabled by default.
    run_real_ai_tests: bool = False
    default_scoring_version: Literal["deterministic-v1", "deterministic-v1.1"] = (
        "deterministic-v1.1"
    )
    embedding_provider: Literal["sentence_transformers", "fake"] = "sentence_transformers"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_device: str = "cpu"
    faiss_index_dir: str = "../data/faiss"
    semantic_top_k: int = 5
    semantic_similarity_threshold: float = 0.25
    dify_base_url: str | None = None
    dify_resume_optimization_api_key: str | None = None
    dify_resume_optimization_workflow_version: str = "resume-optimization-v1"
    # Career Assistant knowledge QA workflow.
    dify_knowledge_qa_api_key: str | None = None
    dify_knowledge_qa_workflow_version: str = "knowledge-qa-v1"
    knowledge_qa_top_k: int = 5
    knowledge_qa_similarity_threshold: float = 0.25
    knowledge_qa_context_chunks: int = 5
    # Knowledge document indexing runs outside the HTTP request lifecycle.
    knowledge_index_stale_after_seconds: int = 900
    # Optional chat interview workflows.
    dify_interview_plan_api_key: str | None = None
    dify_interview_plan_workflow_version: str = "interview-plan-v1"
    dify_interview_chat_api_key: str | None = None
    dify_interview_chat_workflow_version: str = "interview-chat-turn-v1"
    dify_interview_final_api_key: str | None = None
    dify_interview_final_workflow_version: str = "interview-final-evaluation-v1"
    dify_timeout_seconds: float = 60.0
    dify_provider_mode: Literal["fake", "dify"] = "fake"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def ai_mode(self) -> Literal["demo", "mixed", "real"]:
        """Expose the effective AI mode without introducing a second source of truth."""
        if self.ai_provider == "mock" and self.dify_provider_mode == "fake":
            return "demo"
        if self.ai_provider == "openai_compatible" and self.dify_provider_mode == "dify":
            return "real"
        return "mixed"

    @property
    def should_seed_demo_admin(self) -> bool:
        return self.demo_admin_enabled and self.app_env.casefold() in {
            "demo",
            "development",
            "local",
        }

    @property
    def resume_max_upload_bytes(self) -> int:
        return self.resume_max_upload_mb * 1024 * 1024

    def validate_runtime_security(self) -> None:
        development_secret = "change-this-development-key-before-production"
        if self.is_production and (
            len(self.jwt_secret_key) < 32 or self.jwt_secret_key == development_secret
        ):
            raise RuntimeError("JWT_SECRET_KEY must be a non-default 32+ character production key")
        if not self.database_url.startswith("sqlite"):
            raise RuntimeError("DATABASE_URL must use SQLite")
        if (
            min(
                self.login_rate_limit_attempts,
                self.login_rate_limit_window_seconds,
                self.login_rate_limit_lock_seconds,
            )
            <= 0
        ):
            raise RuntimeError("Login rate-limit settings must be positive")
        if self.knowledge_index_stale_after_seconds <= 0:
            raise RuntimeError("Knowledge index stale timeout must be positive")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_runtime_security()
    return settings
