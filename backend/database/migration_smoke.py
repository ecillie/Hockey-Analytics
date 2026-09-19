"""Minimal post-migration API smoke checks against an empty migrated database."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import SessionLocal
from app.main import app


def validate_reference_data(session) -> None:
    source_codes = session.execute(
        text("SELECT code FROM data_sources ORDER BY code")
    ).scalars().all()
    season_count = session.execute(text("SELECT COUNT(*) FROM seasons")).scalar_one()
    if source_codes != ["capwages", "moneypuck", "nhl"] or season_count != 22:
        raise RuntimeError(
            "initial reference data is incomplete: "
            f"sources={source_codes} seasons={season_count}"
        )


def smoke_checks(client) -> None:
    checks = {
        "/api/health": lambda body: isinstance(body, dict) and body == {"status": "ok"},
        "/api/seasons": lambda body: (
            isinstance(body, dict)
            and bool(body.get("availableSeasons"))
            and isinstance(body.get("currentSeason"), int)
            and body["currentSeason"] >= 2005
        ),
        "/api/teams": lambda body: body == [],
    }
    for path, validate in checks.items():
        response = client.get(path)
        try:
            body = response.json()
        except ValueError:
            body = None
        if response.status_code != 200 or not validate(body):
            raise RuntimeError(
                f"post-migration smoke check failed for {path}: "
                f"status={response.status_code} body={response.text}"
            )


def main() -> int:
    with SessionLocal() as session:
        validate_reference_data(session)
        print("PASS initial reference data")

    with TestClient(app) as client:
        smoke_checks(client)
        print("PASS /api/health")
        print("PASS /api/seasons")
        print("PASS /api/teams")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
