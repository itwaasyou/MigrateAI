import json

from migrateai.analyzer import analyze_repository


def test_extracts_manifest_import_and_database_evidence(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"express": "^4"}})
    )
    (tmp_path / "app.js").write_text(
        "const mongoose = require('mongoose');\napp.get('/users', handler);\n"
    )
    result = analyze_repository(tmp_path)
    assert result.file_count == 2
    assert "express" in result.technologies
    assert result.api_routes[0].start_line == 2
    assert result.database_access[0].file == "app.js"


def test_reports_python_parse_failure_as_incomplete(tmp_path):
    (tmp_path / "broken.py").write_text("def nope(:\n")
    result = analyze_repository(tmp_path)
    assert result.status == "incomplete"
    assert any("syntax could not be parsed" in warning for warning in result.warnings)
