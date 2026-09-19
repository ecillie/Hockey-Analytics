"""Checks for the committed frontend/backend API contract artifact."""

from __future__ import annotations

import json
from pathlib import Path

from app.main import app


ROOT = Path(__file__).resolve().parents[2]
OPENAPI = ROOT / "docs" / "openapi.json"


def test_committed_openapi_schema_matches_backend():
    assert json.loads(OPENAPI.read_text(encoding="utf-8")) == app.openapi()


def test_every_public_route_has_success_and_shared_error_schemas():
    schema = app.openapi()
    operations = [path["get"] for path in schema["paths"].values()]

    assert len(operations) == 18
    for operation in operations:
        responses = operation["responses"]
        assert "200" in responses
        assert "422" not in responses
        for status in ("400", "404", "500", "503"):
            response_schema = responses[status]["content"]["application/json"]["schema"]
            assert response_schema["$ref"] == "#/components/schemas/ErrorResponse"
