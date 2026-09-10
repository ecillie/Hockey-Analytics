import os
import unittest
from unittest.mock import Mock

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

os.environ.setdefault("ENV", "dev")
os.environ.setdefault("DATABASE_URL", "postgresql://example.test/tradevalue")

from app.api.routes import get_service  # noqa: E402
from app.main import create_app  # noqa: E402


TEAM = {
    "id": 1, "nhlTeamId": 10, "abbreviation": "TOR",
    "name": "Toronto Maple Leafs", "city": "Toronto", "active": True,
}
PLAYER = {
    "id": 7, "firstName": "Test", "lastName": "Player", "fullName": "Test Player",
    "birthDate": "2000-01-01", "age": 26, "primaryPosition": "C",
    "shootsCatches": "L", "nationality": "CAN", "active": True,
    "rosterStatus": "ACTIVE", "team": TEAM,
}
SUMMARY = {
    **PLAYER, "season": 2025, "gamesPlayed": 82, "goals": 30, "assists": 50,
    "points": 80, "toiSeconds": 90000, "gameScore": 50.0, "gameScorePer60": 2.0,
    "hockeyValue": 22.0, "projectedNextSeasonHockeyValue": None,
    "capHitCents": 800000000,
}


class StubService:
    def __init__(self):
        self.session = Mock()

    def current_season(self):
        return 2025

    def seasons(self):
        return {"currentSeason": 2025, "availableSeasons": [{"startYear": 2025, "endYear": 2026, "label": "2025-26", "salaryCapCents": 9550000000}]}

    def players(self, *_args):
        return {"data": [SUMMARY], "pagination": {"page": 1, "pageSize": 25, "totalItems": 1, "totalPages": 1}}

    def player_identity(self, _player_id):
        return PLAYER

    def teams(self):
        return [TEAM]

    def search(self, _query, _types, _limit):
        return {"players": [], "teams": []}

    def compare(self, ids, season):
        raise AssertionError(f"valid comparison was not expected: {ids}, {season}")


class ApiContractTests(unittest.TestCase):
    def setUp(self):
        app = create_app()
        self.stub = StubService()
        app.dependency_overrides[get_service] = lambda: self.stub
        self.client = TestClient(app, raise_server_exceptions=False)
        self.app = app

    def test_all_documented_routes_are_exposed(self):
        paths = set(self.app.openapi()["paths"])
        self.assertEqual(paths, {
            "/api/health", "/api/seasons", "/api/players", "/api/players/compare",
            "/api/players/{player_id}", "/api/players/{player_id}/stats",
            "/api/players/{player_id}/seasons", "/api/players/{player_id}/value",
            "/api/players/{player_id}/value/history", "/api/players/{player_id}/contract",
            "/api/rankings/hockey-value", "/api/teams", "/api/teams/{team_id}",
            "/api/teams/{team_id}/roster", "/api/teams/{team_id}/contracts",
            "/api/teams/{team_id}/cap", "/api/search", "/api/overview",
        })

    def test_health_checks_database_and_returns_contract_shape(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.stub.session.execute.assert_called_once()

    def test_database_failure_uses_shared_503_error_envelope(self):
        self.stub.session.execute.side_effect = OperationalError(
            "SELECT 1", {}, Exception("database unavailable")
        )
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {
                "error": {
                    "code": "DATABASE_UNAVAILABLE",
                    "message": "The data service is temporarily unavailable.",
                }
            },
        )

    def test_response_models_emit_camel_case_contract(self):
        response = self.client.get("/api/players?season=2025")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"][0]["fullName"], "Test Player")
        self.assertEqual(response.json()["data"][0]["capHitCents"], 800000000)

    def test_invalid_query_uses_shared_400_error_envelope(self):
        response = self.client.get("/api/players?pageSize=101")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "INVALID_REQUEST")
        self.assertIn("pageSize", response.json()["error"]["details"])

    def test_comparison_rejects_duplicates(self):
        response = self.client.get("/api/players/compare?ids=7,7&season=2025")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "INVALID_COMPARISON")

    def test_search_rejects_whitespace_only_query(self):
        response = self.client.get("/api/search", params={"q": "  "})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "INVALID_REQUEST")

    def test_cors_allows_local_frontend(self):
        response = self.client.options(
            "/api/players",
            headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:5173")


if __name__ == "__main__":
    unittest.main()
