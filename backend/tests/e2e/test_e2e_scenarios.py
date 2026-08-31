"""E2E test scenarios (Task 8.2).

These tests exercise the full API stack with a mock LLM provider.
They run in the standard CI pipeline (not integration-only).
"""

from __future__ import annotations

import io
import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


class TestFirstTimeUserFlow:
    """Scenario 1: App launches, create class, upload file, browse wiki, query."""

    async def test_health_check(self, e2e_client: AsyncClient) -> None:
        resp = await e2e_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_create_class_and_upload(
        self, e2e_client: AsyncClient, sample_source_file
    ) -> None:
        resp = await e2e_client.post(
            "/api/classes",
            json={"name": "My First Class", "description": "Testing"},
        )
        assert resp.status_code == 201
        class_data = resp.json()
        class_id = class_data["id"]
        assert class_data["name"] == "My First Class"

        resp = await e2e_client.post(
            f"/api/classes/{class_id}/files",
            files={
                "files": (
                    "test_notes.md",
                    io.BytesIO(sample_source_file.read_bytes()),
                    "text/markdown",
                )
            },
        )
        assert resp.status_code == 202
        uploads = resp.json()
        assert len(uploads) == 1
        assert uploads[0]["original_filename"] == "test_notes.md"

    async def test_list_classes_returns_stats(
        self, e2e_class: dict, e2e_client: AsyncClient
    ) -> None:
        resp = await e2e_client.get("/api/classes")
        assert resp.status_code == 200
        classes = resp.json()
        assert len(classes) >= 1
        found = next(c for c in classes if c["id"] == e2e_class["id"])
        assert "file_count" in found
        assert "page_count" in found


class TestClassOperations:
    """Scenario 5: Class CRUD and isolation."""

    async def test_create_and_get_class(self, e2e_client: AsyncClient) -> None:
        resp = await e2e_client.post(
            "/api/classes",
            json={"name": "Physics 101", "description": "Mechanics"},
        )
        assert resp.status_code == 201
        class_id = resp.json()["id"]

        resp = await e2e_client.get(f"/api/classes/{class_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Physics 101"

    async def test_update_class(self, e2e_class: dict, e2e_client: AsyncClient) -> None:
        class_id = e2e_class["id"]
        resp = await e2e_client.put(
            f"/api/classes/{class_id}",
            json={"name": "Updated Name"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

    async def test_delete_class(self, e2e_client: AsyncClient) -> None:
        resp = await e2e_client.post(
            "/api/classes",
            json={"name": "To Delete"},
        )
        class_id = resp.json()["id"]

        resp = await e2e_client.delete(f"/api/classes/{class_id}")
        assert resp.status_code == 204

        resp = await e2e_client.get(f"/api/classes/{class_id}")
        assert resp.status_code == 404

    async def test_class_not_found(self, e2e_client: AsyncClient) -> None:
        fake_id = str(uuid.uuid4())
        resp = await e2e_client.get(f"/api/classes/{fake_id}")
        assert resp.status_code == 404
        body = resp.json()
        assert "detail" in body

    async def test_class_isolation_files(self, e2e_client: AsyncClient, tmp_path) -> None:
        resp1 = await e2e_client.post("/api/classes", json={"name": "Class A"})
        resp2 = await e2e_client.post("/api/classes", json={"name": "Class B"})
        id_a = resp1.json()["id"]
        id_b = resp2.json()["id"]

        f = tmp_path / "class_a_notes.md"
        f.write_text("# Class A content")
        await e2e_client.post(
            f"/api/classes/{id_a}/files",
            files={"files": ("notes_a.md", io.BytesIO(f.read_bytes()), "text/markdown")},
        )

        resp = await e2e_client.get(f"/api/classes/{id_b}/files")
        assert resp.status_code == 200
        assert len(resp.json()) == 0


class TestFileUpload:
    """Scenario 2: Multi-file upload and status tracking."""

    async def test_upload_multiple_files(
        self, e2e_client: AsyncClient, e2e_class: dict, sample_files: dict
    ) -> None:
        class_id = e2e_class["id"]

        file_list = []
        for path in sample_files.values():
            file_list.append(("files", (path.name, io.BytesIO(path.read_bytes()), "text/markdown")))

        resp = await e2e_client.post(f"/api/classes/{class_id}/files", files=file_list)
        assert resp.status_code == 202
        uploads = resp.json()
        assert len(uploads) == 3

    async def test_list_uploaded_files(
        self, e2e_client: AsyncClient, e2e_class: dict, sample_source_file
    ) -> None:
        class_id = e2e_class["id"]
        await e2e_client.post(
            f"/api/classes/{class_id}/files",
            files={
                "files": ("test.md", io.BytesIO(sample_source_file.read_bytes()), "text/markdown")
            },
        )

        resp = await e2e_client.get(f"/api/classes/{class_id}/files")
        assert resp.status_code == 200
        files = resp.json()
        assert len(files) >= 1


class TestWikiOperations:
    """Scenarios 3, 6, 7: Wiki browse, edit, export, lint."""

    async def test_wiki_tree_empty(self, e2e_client: AsyncClient, e2e_class: dict) -> None:
        class_id = e2e_class["id"]
        resp = await e2e_client.get(f"/api/classes/{class_id}/wiki/tree")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_wiki_export(self, e2e_client: AsyncClient, e2e_class: dict) -> None:
        class_id = e2e_class["id"]
        resp = await e2e_client.post(f"/api/classes/{class_id}/wiki/export")
        # Empty wiki may return 400 (no pages to export) or 200 with empty zip
        assert resp.status_code in (200, 400)
        if resp.status_code == 200:
            assert resp.headers.get("content-type") in (
                "application/zip",
                "application/x-zip-compressed",
                "application/octet-stream",
            )

    async def test_wiki_search_empty(self, e2e_client: AsyncClient, e2e_class: dict) -> None:
        class_id = e2e_class["id"]
        resp = await e2e_client.get(f"/api/classes/{class_id}/wiki/search", params={"q": "test"})
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data


class TestBackupRoundTrip:
    """Scenario 8: Backup export and import preserve data."""

    async def test_export_backup(self, e2e_client: AsyncClient, e2e_class: dict) -> None:
        class_id = e2e_class["id"]
        resp = await e2e_client.post(f"/api/classes/{class_id}/backup")
        assert resp.status_code == 200
        assert len(resp.content) > 0

    async def test_backup_round_trip(
        self, e2e_client: AsyncClient, e2e_class: dict, sample_source_file
    ) -> None:
        class_id = e2e_class["id"]
        await e2e_client.post(
            f"/api/classes/{class_id}/files",
            files={
                "files": ("notes.md", io.BytesIO(sample_source_file.read_bytes()), "text/markdown")
            },
        )

        resp = await e2e_client.post(f"/api/classes/{class_id}/backup")
        assert resp.status_code == 200
        backup_data = resp.content

        await e2e_client.delete(f"/api/classes/{class_id}")

        resp = await e2e_client.post(
            "/api/classes/import",
            files={"file": ("backup.zip", io.BytesIO(backup_data), "application/zip")},
        )
        assert resp.status_code == 201
        imported = resp.json()
        assert imported["id"] != class_id
        assert imported["name"].startswith("E2E Test Class")


class TestErrorHandling:
    """Verify structured error responses across endpoints."""

    async def test_404_has_structured_error(self, e2e_client: AsyncClient) -> None:
        resp = await e2e_client.get(f"/api/classes/{uuid.uuid4()}")
        assert resp.status_code == 404
        body = resp.json()
        assert "detail" in body
        assert "code" in body

    async def test_invalid_class_id_format(self, e2e_client: AsyncClient) -> None:
        resp = await e2e_client.get("/api/classes/not-a-uuid")
        assert resp.status_code == 422

    async def test_create_class_missing_name(self, e2e_client: AsyncClient) -> None:
        resp = await e2e_client.post("/api/classes", json={})
        assert resp.status_code == 422


class TestTasksAPI:
    """Verify tasks endpoint returns proper responses."""

    async def test_list_tasks_empty(self, e2e_client: AsyncClient) -> None:
        resp = await e2e_client.get("/api/tasks")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_task_not_found(self, e2e_client: AsyncClient) -> None:
        resp = await e2e_client.get(f"/api/tasks/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestSettingsAPI:
    """Verify settings endpoints work."""

    async def test_get_settings(self, e2e_client: AsyncClient) -> None:
        resp = await e2e_client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert "llm_provider" in data

    async def test_update_settings(self, e2e_client: AsyncClient) -> None:
        resp = await e2e_client.put(
            "/api/settings",
            json={"llm_provider": "anthropic"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["llm_provider"] == "anthropic"

    async def test_get_usage(self, e2e_client: AsyncClient) -> None:
        resp = await e2e_client.get("/api/settings/usage")
        assert resp.status_code == 200
        data = resp.json()
        assert "input_tokens" in data
        assert "request_count" in data
