from pathlib import Path

from app.core.config import get_settings


def main() -> None:
    settings = get_settings()
    settings.validate_runtime_security()
    if settings.ai_mode != "demo":
        raise RuntimeError(
            "Demo startup requires AI_PROVIDER=mock and DIFY_PROVIDER_MODE=fake"
        )
    database_kind = "SQLite" if settings.database_url.startswith("sqlite") else "unsupported"
    embedding_needs_download = (
        settings.embedding_provider == "sentence_transformers"
        and not Path(settings.embedding_model).exists()
    )

    print("CareerPilot demo configuration")
    print(f"- environment: {settings.app_env}")
    print(f"- database: {database_kind}")
    print(f"- AI provider: {settings.ai_provider}")
    print(f"- chat model: {settings.openai_chat_model}")
    print(f"- chat API key configured: {bool(settings.openai_api_key)}")
    print(f"- embedding provider: {settings.embedding_provider}")
    print(f"- embedding model: {settings.embedding_model}")
    print(f"- first semantic run may download model: {embedding_needs_download}")
    print("- secrets: values intentionally hidden")


if __name__ == "__main__":
    main()
