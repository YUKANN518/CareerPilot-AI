from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.models.users import User


async def register_headers(
    client: AsyncClient,
    email: str,
) -> dict[str, str]:
    response = await client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "StrongPassword123!",
            "display_name": "Job Center User",
        },
    )
    assert response.status_code == 201
    token = response.json()["data"]["tokens"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def manual_job_payload() -> dict[str, object]:
    return {
        "external_job_id": "private-1",
        "title": "Platform Engineer",
        "company": "CareerPilot Labs",
        "location": "Shanghai",
        "salary_min": 30000,
        "salary_max": 45000,
        "currency": "CNY",
        "employment_type": "FULL_TIME",
        "experience_level": "MID",
        "education_requirement": "BACHELOR",
        "description": "Build reliable developer platforms.",
        "requirements": "Python, SQL and containers.",
        "source_url": "https://jobs.example.com/platform-engineer",
        "skills": ["Python", "SQL"],
    }


async def test_manual_import_favorite_and_user_isolation(
    client: AsyncClient,
    db_session: Session,
) -> None:
    first_headers = await register_headers(client, "first-job-user@example.com")
    second_headers = await register_headers(client, "second-job-user@example.com")

    imported = await client.post(
        "/api/jobs/manual",
        headers=first_headers,
        json=manual_job_payload(),
    )
    assert imported.status_code == 201, imported.text
    data = imported.json()["data"]
    assert data["imported_count"] == 1
    assert data["items"][0]["skills"] == ["Python", "SQL"]
    job_id = data["items"][0]["id"]

    duplicate = await client.post(
        "/api/jobs/manual",
        headers=first_headers,
        json=manual_job_payload(),
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["data"]["duplicate_count"] == 1

    favorite = await client.post(f"/api/jobs/{job_id}/favorite", headers=first_headers)
    assert favorite.status_code == 200
    assert favorite.json()["data"]["is_favorite"] is True

    favorites = await client.get("/api/jobs/favorites", headers=first_headers)
    assert favorites.status_code == 200
    assert [item["id"] for item in favorites.json()["data"]["items"]] == [job_id]

    hidden = await client.get(f"/api/jobs/{job_id}", headers=second_headers)
    hidden_favorite = await client.post(
        f"/api/jobs/{job_id}/favorite",
        headers=second_headers,
    )
    assert hidden.status_code == 404
    assert hidden_favorite.status_code == 404

    updated = await client.patch(
        f"/api/jobs/{job_id}",
        headers=first_headers,
        json={"company": "Updated CareerPilot Labs"},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["company"] == "Updated CareerPilot Labs"
    hidden_update = await client.patch(
        f"/api/jobs/{job_id}",
        headers=second_headers,
        json={"company": "Other user's company"},
    )
    assert hidden_update.status_code == 404

    private_list = await client.get(
        "/api/jobs",
        headers=first_headers,
        params={"visibility": "PRIVATE", "limit": 20},
    )
    assert private_list.status_code == 200
    private_data = private_list.json()["data"]
    assert [item["id"] for item in private_data["items"]] == [job_id]
    assert private_data["page"] == 1
    assert private_data["page_size"] == 20
    assert private_data["total_pages"] == 1

    hidden_private_list = await client.get(
        "/api/jobs",
        headers=second_headers,
        params={"visibility": "PRIVATE"},
    )
    assert hidden_private_list.status_code == 200
    assert hidden_private_list.json()["data"]["items"] == []

    removed = await client.delete(f"/api/jobs/{job_id}/favorite", headers=first_headers)
    assert removed.status_code == 200
    assert removed.json()["data"]["is_favorite"] is False
    assert db_session.get(User, 1) is not None


async def test_manual_preview_allows_missing_company_and_requires_content(
    client: AsyncClient,
) -> None:
    headers = await register_headers(client, "private-preview@example.com")
    payload = {
        "title": "Data Engineer",
        "company": "",
        "requirements": "Experience building reliable data pipelines.",
    }
    preview = await client.post("/api/jobs/manual/preview", headers=headers, json=payload)
    assert preview.status_code == 200, preview.text
    assert preview.json()["data"]["company"] == "未提供"
    assert preview.json()["data"]["description"] == payload["requirements"]

    imported = await client.post("/api/jobs/manual", headers=headers, json=payload)
    assert imported.status_code == 201, imported.text
    assert imported.json()["data"]["items"][0]["company"] == "未提供"

    invalid = await client.post(
        "/api/jobs/manual",
        headers=headers,
        json={"title": "Incomplete job", "description": "  ", "requirements": ""},
    )
    assert invalid.status_code == 422


async def test_csv_import_validation_filtering_and_duplicate_rows(
    client: AsyncClient,
) -> None:
    headers = await register_headers(client, "csv-job-user@example.com")
    missing_column = await client.post(
        "/api/jobs/import-csv",
        headers=headers,
        json={
            "csv_content": "role,company\nEngineer,CSV Corp\n",
            "field_mapping": {
                "title": "role",
                "company": "company",
                "description": "description",
            },
        },
    )
    assert missing_column.status_code == 422
    assert missing_column.json()["error"]["code"] == "CSV_COLUMNS_MISSING"

    imported = await client.post(
        "/api/jobs/import-csv",
        headers=headers,
        json={
            "csv_content": (
                "role,company,description,location\n"
                "Data Engineer,CSV Corp,Build pipelines,Beijing\n"
                "Data Engineer,CSV Corp,Build pipelines,Beijing\n"
            ),
            "field_mapping": {
                "title": "role",
                "company": "company",
                "description": "description",
                "location": "location",
            },
        },
    )
    assert imported.status_code == 201, imported.text
    assert imported.json()["data"]["imported_count"] == 1
    assert imported.json()["data"]["duplicate_count"] == 1

    filtered = await client.get(
        "/api/jobs",
        headers=headers,
        params={
            "search": "Data",
            "location": "Beijing",
            "company": "CSV Corp",
            "sort": "title_asc",
        },
    )
    assert filtered.status_code == 200
    assert filtered.json()["data"]["total"] == 1
    assert filtered.json()["data"]["items"][0]["source_type"] == "USER_CSV"

