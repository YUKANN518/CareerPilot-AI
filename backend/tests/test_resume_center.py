from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.providers.base import ProviderResponse, ResumeAIProvider
from app.ai.providers.mock import MockAIProvider
from app.api.dependencies import get_resume_ai_provider
from app.core.config import Settings
from app.main import app
from app.models.resumes import FileAsset, Resume, ResumeSkill, ResumeVersion
from app.schemas.resume import TextBlock

FIXTURES = Path(__file__).parent / "fixtures"
PASSWORD = "StrongPassword123!"


async def register_and_headers(
    client: AsyncClient,
    email: str = "resume-owner@example.com",
) -> dict[str, str]:
    response = await client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "display_name": "Resume Owner",
        },
    )
    assert response.status_code == 201
    token = response.json()["data"]["tokens"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def sample_file(filename: str) -> bytes:
    return (FIXTURES / filename).read_bytes()


async def upload(
    client: AsyncClient,
    headers: dict[str, str],
    filename: str = "sample_resume.pdf",
    content: bytes | None = None,
    mime_type: str = "application/pdf",
) -> tuple[int, dict[str, object]]:
    response = await client.post(
        "/api/resumes/upload",
        headers=headers,
        files={
            "file": (filename, content if content is not None else sample_file(filename), mime_type)
        },
    )
    return response.status_code, response.json()


async def prepare_extracted_resume(
    client: AsyncClient,
    headers: dict[str, str],
) -> int:
    status_code, body = await upload(client, headers)
    assert status_code == 201
    resume_id = int(body["data"]["resume"]["id"])
    extraction = await client.post(
        f"/api/resumes/{resume_id}/extract",
        headers=headers,
    )
    assert extraction.status_code == 200
    return resume_id


async def test_upload_valid_pdf_and_extract_text(client: AsyncClient) -> None:
    headers = await register_and_headers(client)

    status_code, body = await upload(client, headers)
    resume_id = body["data"]["resume"]["id"]
    extraction = await client.post(f"/api/resumes/{resume_id}/extract", headers=headers)

    assert status_code == 201
    assert body["data"]["resume"]["file"]["file_format"] == "pdf"
    assert extraction.status_code == 200
    assert extraction.json()["data"]["character_count"] > 100
    assert extraction.json()["data"]["blocks"][0]["page_number"] == 1


async def test_upload_valid_docx_and_extract_paragraphs_and_table(
    client: AsyncClient,
) -> None:
    headers = await register_and_headers(client)
    mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    status_code, body = await upload(
        client,
        headers,
        "sample_resume.docx",
        mime_type=mime,
    )
    resume_id = body["data"]["resume"]["id"]
    extraction = await client.post(f"/api/resumes/{resume_id}/extract", headers=headers)
    blocks = extraction.json()["data"]["blocks"]

    assert status_code == 201
    assert extraction.status_code == 200
    assert any(block["source_type"] == "paragraph" for block in blocks)
    assert any(block["source_type"] == "table" for block in blocks)


@pytest.mark.parametrize(
    ("filename", "content", "mime_type", "expected_status", "expected_code"),
    [
        (
            "pretend.docx",
            b"%PDF-1.4 pretend",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            415,
            "FILE_SIGNATURE_MISMATCH",
        ),
        ("empty.pdf", b"", "application/pdf", 400, "EMPTY_FILE"),
    ],
)
async def test_upload_rejects_invalid_files(
    client: AsyncClient,
    filename: str,
    content: bytes,
    mime_type: str,
    expected_status: int,
    expected_code: str,
) -> None:
    headers = await register_and_headers(client)

    status_code, body = await upload(client, headers, filename, content, mime_type)

    assert status_code == expected_status
    assert body["error"]["code"] == expected_code


async def test_upload_rejects_oversized_file(client: AsyncClient) -> None:
    headers = await register_and_headers(client)

    status_code, body = await upload(
        client,
        headers,
        "large.pdf",
        b"%PDF-" + b"x" * (10 * 1024 * 1024),
    )

    assert status_code == 413
    assert body["error"]["code"] == "FILE_TOO_LARGE"


async def test_sha256_duplicate_returns_existing_resume(
    client: AsyncClient,
    db_session: Session,
) -> None:
    headers = await register_and_headers(client)

    first_status, first = await upload(client, headers)
    second_status, second = await upload(client, headers)

    assert first_status == 201
    assert second_status == 200
    assert second["data"]["duplicate"] is True
    assert second["data"]["resume"]["id"] == first["data"]["resume"]["id"]
    assert db_session.scalar(select(func.count(FileAsset.id))) == 1


async def test_mock_parse_edit_confirm_and_skill_evidence(
    client: AsyncClient,
) -> None:
    headers = await register_and_headers(client)
    resume_id = await prepare_extracted_resume(client, headers)

    parsed = await client.post(f"/api/resumes/{resume_id}/parse", headers=headers)
    profile = parsed.json()["data"]["result"]
    profile["basic_info"]["full_name"]["value"] = "Edited Sample Candidate"
    updated = await client.patch(
        f"/api/resumes/{resume_id}/parse-result",
        headers=headers,
        json=profile,
    )
    confirmed = await client.post(f"/api/resumes/{resume_id}/confirm", headers=headers)
    version_id = confirmed.json()["data"]["id"]
    skills = await client.get(f"/api/resume-versions/{version_id}/skills", headers=headers)

    assert parsed.status_code == 200
    assert parsed.json()["data"]["status"] == "NEEDS_CONFIRMATION"
    assert updated.status_code == 200
    assert confirmed.status_code == 201
    assert confirmed.json()["data"]["structured_data"]["basic_info"]["full_name"]["value"] == (
        "Edited Sample Candidate"
    )
    assert skills.status_code == 200
    assert skills.json()["data"]
    assert all(item["evidence_text"] for item in skills.json()["data"])
    assert all(item["source_location"]["label"] for item in skills.json()["data"])
    assert all(item["is_user_confirmed"] is True for item in skills.json()["data"])


async def test_editing_confirmed_profile_creates_new_immutable_version(
    client: AsyncClient,
) -> None:
    headers = await register_and_headers(client)
    resume_id = await prepare_extracted_resume(client, headers)
    parsed = await client.post(f"/api/resumes/{resume_id}/parse", headers=headers)
    first_profile = parsed.json()["data"]["result"]
    first_profile["summary"]["value"] = "First confirmed summary"
    await client.patch(
        f"/api/resumes/{resume_id}/parse-result",
        headers=headers,
        json=first_profile,
    )
    first = await client.post(f"/api/resumes/{resume_id}/confirm", headers=headers)

    second_profile = first.json()["data"]["structured_data"]
    second_profile["summary"]["value"] = "Second confirmed summary"
    changed = await client.patch(
        f"/api/resumes/{resume_id}/parse-result",
        headers=headers,
        json=second_profile,
    )
    second = await client.post(f"/api/resumes/{resume_id}/confirm", headers=headers)
    first_again = await client.get(
        f"/api/resume-versions/{first.json()['data']['id']}",
        headers=headers,
    )
    versions = await client.get(f"/api/resumes/{resume_id}/versions", headers=headers)

    assert changed.json()["data"]["status"] == "NEEDS_CONFIRMATION"
    assert first.json()["data"]["version_number"] == 1
    assert second.json()["data"]["version_number"] == 2
    assert first_again.json()["data"]["structured_data"]["summary"]["value"] == (
        "First confirmed summary"
    )
    assert [item["version_number"] for item in versions.json()["data"]] == [2, 1]
    assert versions.json()["data"][0]["is_current"] is True
    assert versions.json()["data"][1]["is_current"] is False


class RetryProvider(ResumeAIProvider):
    def __init__(self, valid_on_attempt: int | None) -> None:
        self.valid_on_attempt = valid_on_attempt
        self.attempts = 0
        self.mock = MockAIProvider()

    async def structure_resume(
        self,
        raw_text: str,
        blocks: list[TextBlock],
    ) -> ProviderResponse:
        self.attempts += 1
        if self.valid_on_attempt == self.attempts:
            return await self.mock.structure_resume(raw_text, blocks)
        return ProviderResponse(
            raw_content='{"incomplete": true}',
            provider_name="retry-test",
            model_name="invalid-json-test",
            latency_ms=1,
        )


@pytest.mark.parametrize(
    ("valid_on_attempt", "expected_error"),
    [(3, None), (None, "AI_PARSE_FAILED")],
)
async def test_invalid_ai_output_retries_then_succeeds_or_enters_manual_state(
    client: AsyncClient,
    valid_on_attempt: int | None,
    expected_error: str | None,
) -> None:
    headers = await register_and_headers(client)
    resume_id = await prepare_extracted_resume(client, headers)
    provider = RetryProvider(valid_on_attempt)
    app.dependency_overrides[get_resume_ai_provider] = lambda: provider

    response = await client.post(f"/api/resumes/{resume_id}/parse", headers=headers)

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "NEEDS_CONFIRMATION"
    assert response.json()["data"]["parse_attempts"] == 3
    assert response.json()["data"]["error_code"] == expected_error
    assert provider.attempts == 3


async def test_ownership_isolation_and_illegal_state_transition(
    client: AsyncClient,
) -> None:
    owner_headers = await register_and_headers(client, "owner@example.com")
    other_headers = await register_and_headers(client, "other@example.com")
    status_code, body = await upload(client, owner_headers)
    resume_id = body["data"]["resume"]["id"]

    not_owned = await client.get(f"/api/resumes/{resume_id}", headers=other_headers)
    not_owned_file = await client.get(
        f"/api/resumes/{resume_id}/file",
        headers=other_headers,
    )
    parse_too_early = await client.post(
        f"/api/resumes/{resume_id}/parse",
        headers=owner_headers,
    )

    assert status_code == 201
    assert not_owned.status_code == 404
    assert not_owned_file.status_code == 404
    assert parse_too_early.status_code == 409
    assert parse_too_early.json()["error"]["code"] == "INVALID_RESUME_STATE"


async def test_delete_resume_cascades_versions_and_skills_and_removes_file(
    client: AsyncClient,
    db_session: Session,
    test_settings: Settings,
) -> None:
    headers = await register_and_headers(client)
    resume_id = await prepare_extracted_resume(client, headers)
    await client.post(f"/api/resumes/{resume_id}/parse", headers=headers)
    confirmed = await client.post(f"/api/resumes/{resume_id}/confirm", headers=headers)
    version_id = confirmed.json()["data"]["id"]
    storage_key = db_session.scalar(
        select(FileAsset.storage_key).join(Resume).where(Resume.id == resume_id)
    )
    assert storage_key is not None
    file_path = Path(test_settings.upload_directory) / storage_key

    deleted = await client.delete(f"/api/resumes/{resume_id}", headers=headers)

    assert deleted.status_code == 200
    assert db_session.get(Resume, resume_id) is None
    assert db_session.get(ResumeVersion, version_id) is None
    assert db_session.scalar(select(func.count(ResumeSkill.id))) == 0
    assert db_session.scalar(select(func.count(FileAsset.id))) == 0
    assert not file_path.exists()
