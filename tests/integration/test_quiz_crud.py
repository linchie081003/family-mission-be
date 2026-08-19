import uuid

import pytest
from httpx import AsyncClient

SAMPLE_QUESTION = {
    "question": "Berapa 3 + 3?",
    "options": ["5", "6", "7"],
    "correct_index": 1,
    "explanation": "3 + 3 = 6",
}


def template_payload(title: str) -> dict:
    return {
        "subject": "Matematika",
        "title": title,
        "grade_level": "SD",
        "description": "Integration test",
        "questions": [SAMPLE_QUESTION],
    }


@pytest.mark.asyncio
async def test_quiz_crud_flow(
    client: AsyncClient,
    platform_admin_headers: dict,
    quiz_parent: dict,
    registered_parent: dict,
):
    """Platform template CRUD, parent quiz CRUD, clone flow, and feature guard."""
    title = f"API Template {uuid.uuid4().hex[:6]}"
    create = await client.post(
        "/api/platform/quiz-templates",
        headers=platform_admin_headers,
        json=template_payload(title),
    )
    assert create.status_code == 200, create.text
    tpl = create.json()
    template_id = tpl["id"]

    detail = await client.get(
        f"/api/platform/quiz-templates/{template_id}",
        headers=platform_admin_headers,
    )
    assert detail.status_code == 200
    assert detail.json()["questions"][0]["question"] == SAMPLE_QUESTION["question"]

    updated_title = f"{title} Updated"
    update = await client.put(
        f"/api/platform/quiz-templates/{template_id}",
        headers=platform_admin_headers,
        json={
            **template_payload(updated_title),
            "questions": [
                SAMPLE_QUESTION,
                {"question": "Berapa 1 + 1?", "options": ["1", "2"], "correct_index": 1},
            ],
        },
    )
    assert update.status_code == 200
    assert update.json()["title"] == updated_title
    assert len(update.json()["questions"]) == 2

    parent_headers = quiz_parent["headers"]

    custom = await client.post(
        "/api/quizzes",
        headers=parent_headers,
        json={
            "subject": "Matematika",
            "title": "Custom Quiz",
            "points_reward": 12,
            "passing_score": 70,
            "questions": [SAMPLE_QUESTION],
        },
    )
    assert custom.status_code == 200, custom.text
    quiz_id = custom.json()["id"]

    listed = await client.get("/api/quizzes", headers=parent_headers)
    assert listed.status_code == 200
    assert any(q["id"] == quiz_id for q in listed.json())

    edited = await client.put(
        f"/api/quizzes/{quiz_id}",
        headers=parent_headers,
        json={
            "subject": "Matematika",
            "title": "Custom Quiz Edited",
            "points_reward": 15,
            "passing_score": 75,
            "questions": [SAMPLE_QUESTION],
        },
    )
    assert edited.status_code == 200
    assert edited.json()["title"] == "Custom Quiz Edited"

    clone = await client.post(
        f"/api/quizzes/from-template/{template_id}",
        headers=parent_headers,
        json={"points_reward": 10, "passing_score": 70},
    )
    assert clone.status_code == 200, clone.text
    cloned_id = clone.json()["id"]

    clone_edit = await client.put(
        f"/api/quizzes/{cloned_id}",
        headers=parent_headers,
        json={
            "subject": "Matematika",
            "title": "Clone Edited",
            "points_reward": 10,
            "passing_score": 70,
            "questions": [SAMPLE_QUESTION],
        },
    )
    assert clone_edit.status_code == 200
    assert clone_edit.json()["template_id"] == template_id

    deactivate = await client.patch(
        f"/api/quizzes/{quiz_id}",
        headers=parent_headers,
        json={"is_active": False},
    )
    assert deactivate.status_code == 200
    assert deactivate.json()["is_active"] is False

    soft_delete_tpl = await client.delete(
        f"/api/platform/quiz-templates/{template_id}",
        headers=platform_admin_headers,
    )
    assert soft_delete_tpl.status_code == 200
    assert soft_delete_tpl.json()["deleted"] is False

    toggle = await client.patch(
        f"/api/platform/quiz-templates/{template_id}/active?is_active=false",
        headers=platform_admin_headers,
    )
    assert toggle.status_code == 200

    blocked = await client.get("/api/quizzes", headers=registered_parent["headers"])
    assert blocked.status_code == 403
