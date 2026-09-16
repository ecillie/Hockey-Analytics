from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.database import container_smoke


def test_validate_retries_readiness_then_checks_all_routes():
    responses = [
        (503, None, "starting"),
        (200, {"status": "ok"}, '{"status":"ok"}'),
        (200, {"status": "ok"}, '{"status":"ok"}'),
        (
            200,
            {"availableSeasons": [2025], "currentSeason": 2025},
            '{"availableSeasons":[2025],"currentSeason":2025}',
        ),
        (200, [], "[]"),
    ]

    with (
        patch.object(container_smoke, "request_json", side_effect=responses) as request,
        patch.object(container_smoke.time, "sleep") as sleep,
    ):
        container_smoke.validate(
            "http://container.test/", attempts=3, delay=0.01, timeout=1
        )

    sleep.assert_called_once_with(0.01)
    assert [call.args[0] for call in request.call_args_list] == [
        "http://container.test/api/health",
        "http://container.test/api/health",
        "http://container.test/api/health",
        "http://container.test/api/seasons",
        "http://container.test/api/teams",
    ]


def test_validate_reports_readiness_failure_without_running_other_checks():
    with (
        patch.object(
            container_smoke,
            "request_json",
            return_value=(503, None, "database unavailable"),
        ) as request,
        patch.object(container_smoke.time, "sleep"),
        pytest.raises(RuntimeError, match="did not become healthy"),
    ):
        container_smoke.validate(
            "http://container.test", attempts=2, delay=0, timeout=1
        )

    assert request.call_count == 2


def test_validate_retries_a_connection_reset_during_container_startup():
    responses = [
        ConnectionResetError("server restarted the connection"),
        (200, {"status": "ok"}, "ok"),
        (200, {"status": "ok"}, "ok"),
        (
            200,
            {"availableSeasons": [2025], "currentSeason": 2025},
            "seasons",
        ),
        (200, [], "teams"),
    ]

    with (
        patch.object(container_smoke, "request_json", side_effect=responses),
        patch.object(container_smoke.time, "sleep") as sleep,
    ):
        container_smoke.validate(
            "http://container.test", attempts=2, delay=0.01, timeout=1
        )

    sleep.assert_called_once_with(0.01)


@pytest.mark.parametrize(
    ("path", "invalid_response"),
    [
        ("/api/health", (200, {"status": "degraded"}, "degraded")),
        ("/api/seasons", (200, {"availableSeasons": []}, "empty")),
        ("/api/teams", (200, {}, "not a list")),
    ],
)
def test_validate_rejects_invalid_deployed_contract(path, invalid_response):
    valid = {
        "/api/health": (200, {"status": "ok"}, "ok"),
        "/api/seasons": (
            200,
            {"availableSeasons": [2025], "currentSeason": 2025},
            "seasons",
        ),
        "/api/teams": (200, [], "teams"),
    }
    calls = [valid["/api/health"]]
    for check_path in container_smoke.CHECKS:
        calls.append(invalid_response if check_path == path else valid[check_path])

    with (
        patch.object(container_smoke, "request_json", side_effect=calls),
        pytest.raises(RuntimeError, match=f"smoke check failed for {path}"),
    ):
        container_smoke.validate(
            "http://container.test", attempts=1, delay=0, timeout=1
        )
