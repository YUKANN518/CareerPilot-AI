from httpx import AsyncClient


async def register_headers(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "StrongPassword123!",
            "display_name": "Application User",
        },
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['data']['tokens']['access_token']}"}


async def create_private_job(client: AsyncClient, headers: dict[str, str]) -> int:
    response = await client.post(
        "/api/jobs/manual",
        headers=headers,
        json={
            "title": "Backend Engineer",
            "company": "CareerPilot Labs",
            "location": "Hong Kong",
            "description": "Build reliable Python APIs.",
        },
    )
    assert response.status_code == 201, response.text
    return int(response.json()["data"]["items"][0]["id"])


async def test_application_lifecycle_board_and_history(client: AsyncClient) -> None:
    headers = await register_headers(client, "application-owner@example.com")
    job_id = await create_private_job(client, headers)

    created = await client.post(
        "/api/applications",
        headers=headers,
        json={
            "job_id": job_id,
            "status": "SAVED",
            "notes": "Tailor resume before applying.",
        },
    )
    assert created.status_code == 201, created.text
    application = created.json()["data"]
    application_id = application["id"]
    assert application["job"]["title"] == "Backend Engineer"
    assert application["status_history"][0]["from_status"] is None
    assert application["status_history"][0]["to_status"] == "SAVED"

    duplicate = await client.post(
        "/api/applications",
        headers=headers,
        json={"job_id": job_id},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "APPLICATION_EXISTS"

    applied = await client.post(
        f"/api/applications/{application_id}/status",
        headers=headers,
        json={"status": "APPLIED", "note": "Submitted through the company portal."},
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["data"]["status"] == "APPLIED"
    assert applied.json()["data"]["status_history"][-1]["from_status"] == "SAVED"

    interview = await client.post(
        f"/api/applications/{application_id}/status",
        headers=headers,
        json={"status": "INTERVIEW"},
    )
    assert interview.status_code == 200

    board = await client.get("/api/applications/board", headers=headers)
    assert board.status_code == 200
    assert board.json()["data"]["counts"]["INTERVIEW"] == 1
    assert board.json()["data"]["columns"]["INTERVIEW"][0]["id"] == application_id

    updated = await client.patch(
        f"/api/applications/{application_id}",
        headers=headers,
        json={"notes": "Prepare system-design examples."},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["notes"] == "Prepare system-design examples."


async def test_application_rejects_invalid_transition_and_cross_user_access(
    client: AsyncClient,
) -> None:
    owner_headers = await register_headers(client, "application-first@example.com")
    other_headers = await register_headers(client, "application-second@example.com")
    job_id = await create_private_job(client, owner_headers)
    created = await client.post("/api/applications", headers=owner_headers, json={"job_id": job_id})
    application_id = int(created.json()["data"]["id"])

    invalid = await client.post(
        f"/api/applications/{application_id}/status",
        headers=owner_headers,
        json={"status": "OFFER"},
    )
    assert invalid.status_code == 409
    assert invalid.json()["error"]["code"] == "APPLICATION_STATUS_TRANSITION_INVALID"

    hidden = await client.get(f"/api/applications/{application_id}", headers=other_headers)
    assert hidden.status_code == 404
    hidden_board = await client.get("/api/applications/board", headers=other_headers)
    assert hidden_board.status_code == 200
    assert hidden_board.json()["data"]["counts"]["SAVED"] == 0
