import io
import json
import zipfile

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from migrateai import api as api_module
from migrateai.ai import ProviderResult, retrieve, validate_claims
from migrateai.db import Base, get_db
from migrateai.entities import (
    AnalysisRun,
    DependencyEdge,
    EvidenceRecord,
    RepositoryFile,
    User,
    WorkspaceMember,
)
from migrateai.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    testing_sessions = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False
    )
    monkeypatch.setattr("migrateai.jobs.SessionLocal", testing_sessions)

    def override_db():
        with testing_sessions() as session:
            yield session

    monkeypatch.setattr(api_module, "DATA_ROOT", tmp_path / "repositories")
    monkeypatch.setattr(api_module, "enforce_rate_limit", lambda *_args: None)
    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        test_client.testing_sessions = testing_sessions
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def account(client, email):
    response = client.post(
        "/api/auth/signup",
        json={"email": email, "password": "a-very-long-demo-passphrase"},
    )
    assert response.status_code == 201
    return response.json()["workspace"]["id"]


def test_workspace_scope_and_async_upload_flow(client, monkeypatch):
    workspace_id = account(client, "owner@example.com")
    other = TestClient(app)
    inaccessible_workspace = account(other, "other@example.com")
    assert (
        client.get(f"/api/workspaces/{inaccessible_workspace}/repositories").status_code
        == 404
    )

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("demo/package.json", '{"dependencies":{"express":"^4"}}')
        zf.writestr(
            "demo/server.js",
            "const mongoose = require('mongoose');\\napp.get('/items', handler);\\n",
        )
    response = client.post(
        f"/api/workspaces/{workspace_id}/repositories/upload",
        files={"file": ("demo.zip", archive.getvalue(), "application/zip")},
    )
    assert response.status_code == 202
    analysis_id = response.json()["analysis_id"]
    assert response.json()["status"] == "queued"
    assert client.get(f"/api/analysis/{analysis_id}").json()["status"] in {
        "queued",
        "running",
        "completed",
    }

    with client.testing_sessions() as db:
        run = db.get(AnalysisRun, analysis_id)
        assert run.status == "completed"
        assert run.result["file_count"] == 2
        assert db.query(RepositoryFile).filter_by(analysis_id=analysis_id).count() == 2
        assert db.query(DependencyEdge).filter_by(analysis_id=analysis_id).count() >= 1
        assert db.query(EvidenceRecord).filter_by(analysis_id=analysis_id).count() >= 1

    async def fake_generate(_system, _prompt):
        return ProviderResult(
            body='{"claims":[{"claim":"The code imports Mongoose.","type":"fact","confidence":0.98,"evidence":[{"file":"demo/server.js","start_line":1,"end_line":1}]}]}',
            model="test-provider",
            latency_ms=2,
            prompt_tokens=100,
            output_tokens=30,
        )

    monkeypatch.setattr(api_module, "generate", fake_generate)
    answer = client.post(
        f"/api/analysis/{analysis_id}/chat",
        json={"message": "Where does the code import mongoose?"},
    )
    assert answer.status_code == 200
    assert answer.json()["claims"][0]["evidence"][0]["file"] == "demo/server.js"
    assert client.get(f"/api/analysis/{analysis_id}/chat").json()["messages"]
    configured = client.put(
        f"/api/analysis/{analysis_id}/migration",
        json={
            "current_stack": ["Node.js", "MongoDB"],
            "target_stack": ["Spring Boot", "PostgreSQL"],
        },
    )
    assert configured.status_code == 200

    async def fake_plan(_system, _prompt, **_kwargs):
        return ProviderResult(
            body=json.dumps(
                {
                    "title": "Move the order service to Spring Boot and PostgreSQL",
                    "phases": [
                        {
                            "title": title,
                            "objective": f"{title} for the selected Spring Boot and PostgreSQL target.",
                            "validation": "Run the migration acceptance tests.",
                            "rollback": "Restore the last known-good application release.",
                            "tasks": [
                                {
                                    "title": task_title,
                                    "next_action": "Open demo/server.js and record the POST /orders request and response.",
                                    "description": "This keeps the migration tied to behavior found in the repository.",
                                    "done_when": "The change builds and the focused check passes.",
                                    "affected_files": ["demo/server.js", "invented.py"],
                                }
                            ],
                        }
                        for title, task_title in [
                            ("Baseline", "Record current behavior"),
                            ("Data layer", "Map database access"),
                            ("Service migration", "Migrate API behavior"),
                            ("Validation", "Run target stack checks"),
                        ]
                    ],
                }
            ),
            model="gemini-test-model",
            latency_ms=2,
        )

    monkeypatch.setattr(api_module, "generate", fake_plan)
    response = client.post(f"/api/analysis/{analysis_id}/plans")
    assert response.status_code == 201
    plan = response.json()
    assert len(plan["phases"]) == 4
    assert plan["target_stack"] == ["Spring Boot", "PostgreSQL"]
    assert plan["title"] == "Move the order service to Spring Boot and PostgreSQL"
    assert plan["phases"][0]["tasks"][0]["affected_files"] == ["demo/server.js"]
    assert plan["phases"][0]["tasks"][0]["next_action"].startswith("Open demo/server.js")
    assert plan["phases"][0]["tasks"][0]["done_when"] == "The change builds and the focused check passes."
    exported = client.get(f"/api/plans/{plan['id']}/export")
    assert exported.status_code == 200
    assert "## Phased plan" in exported.text
    simulation = client.post(
        f"/api/analysis/{analysis_id}/simulate",
        json={"target_stack": ["PostgreSQL"]},
    )
    assert simulation.status_code == 200
    assert simulation.json()["metrics"]["database_files"] == 1
    foreign = TestClient(app)
    assert foreign.get(f"/api/analysis/{analysis_id}").status_code == 401
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401


def test_plan_falls_back_when_gemini_free_tier_is_unavailable(client, monkeypatch):
    workspace_id = account(client, "fallback@example.com")
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zip_file:
        zip_file.writestr("demo/app.js", "const mongoose = require('mongoose');\n")
    uploaded = client.post(
        f"/api/workspaces/{workspace_id}/repositories/upload",
        files={"file": ("demo.zip", archive.getvalue(), "application/zip")},
    )
    analysis_id = uploaded.json()["analysis_id"]
    assert client.get(f"/api/analysis/{analysis_id}").json()["status"] == "completed"
    client.put(
        f"/api/analysis/{analysis_id}/migration",
        json={
            "current_stack": ["Node.js", "MongoDB"],
            "target_stack": ["Spring Boot", "PostgreSQL"],
        },
    )

    request = httpx.Request("POST", "https://generativelanguage.googleapis.com")
    unavailable = httpx.Response(503, request=request)

    async def gemini_unavailable(*_args, **_kwargs):
        raise httpx.HTTPStatusError(
            "temporarily unavailable", request=request, response=unavailable
        )

    monkeypatch.setattr(api_module, "generate", gemini_unavailable)
    response = client.post(f"/api/analysis/{analysis_id}/plans")

    assert response.status_code == 201
    plan = response.json()
    assert plan["generation_source"] == "evidence"
    assert plan["title"].startswith("Repository scan plan:")
    assert plan["target_stack"] == ["Spring Boot", "PostgreSQL"]
    assert plan["phases"][1]["tasks"][0]["affected_files"] == ["demo/app.js"]


def test_upload_rejects_unsafe_archive_path(client):
    workspace_id = account(client, "safe@example.com")
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zip_file:
        zip_file.writestr("../escape.txt", "not allowed")
    response = client.post(
        f"/api/workspaces/{workspace_id}/repositories/upload",
        files={"file": ("unsafe.zip", archive.getvalue(), "application/zip")},
    )
    assert response.status_code == 400
    assert "unsafe path" in response.json()["detail"]


def test_viewer_can_read_but_cannot_upload(client):
    workspace_id = account(client, "viewer@example.com")
    with client.testing_sessions() as db:
        user = db.scalar(select(User).where(User.email == "viewer@example.com"))
        member = db.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user.id,
            )
        )
        member.role = "viewer"
        db.commit()
    assert client.get(f"/api/workspaces/{workspace_id}/repositories").status_code == 200
    response = client.post(
        f"/api/workspaces/{workspace_id}/repositories/upload",
        files={"file": ("empty.zip", b"not needed", "application/zip")},
    )
    assert response.status_code == 403


def test_rag_skips_env_files_and_rejects_unretrieved_citations(tmp_path):
    (tmp_path / ".env").write_text("DATABASE_URL=private")
    (tmp_path / "service.py").write_text(
        "def find_user():\n    return database.find('users')\n"
    )
    chunks = retrieve(tmp_path, "where does database find users")
    assert [chunk["file"] for chunk in chunks] == ["service.py"]
    result = validate_claims(
        '{"claims":[{"claim":"Invented","type":"fact","evidence":[{"file":"missing.py","start_line":1,"end_line":1}]}]}',
        chunks,
    )
    assert result["answer"].startswith("Insufficient evidence")
