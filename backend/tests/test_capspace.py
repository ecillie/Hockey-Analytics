from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch
import json

import pytest
import requests

from app.ScriptingFiles.FullDataScript import capspace


FIXTURES = Path(__file__).parent / "fixtures" / "ingestion"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def capwages_html(nhl_id: int | None, season: int = 2010) -> str:
    player = {
        "contracts": [{
            "id": "capwages-contract",
            "type": "Standard Contract",
            "value": "$1,000,000",
            "term": 1,
            "signingDate": "2010-07-01",
            "details": [{
                "season": f"{season}-{str(season + 1)[-2:]}",
                "capHit": "$1,000,000",
            }],
        }],
    }
    if nhl_id is not None:
        player["nhlId"] = nhl_id
    payload = {"props": {"pageProps": {"player": player}}}
    return '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(payload) + "</script>"


def test_datsyuk_fixture_parses_identity_money_team_and_clause():
    contract = capspace.parse_capspace_page(
        fixture("capspace_datsyuk.html"), expected_nhl_id="8467514"
    )[0]

    assert contract.external_id == "datsyuk-2007"
    assert contract.signed_on.isoformat() == "2007-04-06"
    assert contract.term_years == 7
    assert contract.total_value_cents == 4_690_000_000
    assert contract.signing_team == "Detroit Red Wings"
    assert contract.seasons[0].season_start_year == 2008
    assert contract.seasons[0].cap_hit_cents == 670_000_000
    assert contract.seasons[0].base_salary_cents == 670_000_000
    assert contract.seasons[0].signing_bonus_cents == 0
    assert contract.seasons[0].performance_bonus_cents == 0
    assert contract.seasons[0].clause == "NMC"


def test_elc_slide_is_explicit_and_does_not_fake_base_salary():
    contract = capspace.parse_capspace_page(fixture("capspace_elc.html"))[0]

    assert contract.is_entry_level is True
    slide = contract.seasons[0]
    assert slide.is_slide is True
    assert slide.base_salary_cents is None
    assert slide.minors_salary_cents == 9_500_000
    assert slide.cap_hit_cents == 95_000_000
    assert contract.seasons[1].performance_bonus_cents == 55_000_000
    assert contract.seasons[1].clause == "M-NTC"


@pytest.mark.parametrize(
    ("value", "expected"),
    [("$6,700,000", 670_000_000), ("0", 0), ("$1.25", 125), (None, None), ("", None)],
)
def test_money_conversion_is_exact(value, expected):
    assert capspace.money_to_cents(value) == expected


@pytest.mark.parametrize("value", ["garbage", "$-5", "$NaN"])
def test_malformed_money_is_rejected(value):
    with pytest.raises(capspace.CapSpaceParseError):
        capspace.money_to_cents(value)


def test_changed_markup_and_malformed_season_are_not_silently_accepted():
    with pytest.raises(capspace.CapSpaceParseError):
        capspace.parse_capspace_page("<html><body><h1>Changed markup</h1></body></html>")
    with pytest.raises(capspace.CapSpaceParseError):
        capspace.season_start_year("not-a-season")


def test_page_with_no_contracts_is_distinct_from_malformed_markup():
    assert capspace.parse_capspace_page("<h1>Contract History</h1>") == ()


def test_nhl_id_is_the_only_url_identity():
    candidate = capspace.Candidate(7, "Pavel", "Datsyuk", "8467514", (2008, 2009))
    session = Mock()
    session.get.return_value = Mock(status_code=404, headers={}, text="")

    outcome = capspace._fetch_profile(session, candidate)

    assert outcome.url == "https://cap-space.com/person/nhl:8467514"
    assert outcome.status == "not_found"


def test_no_nhl_id_never_fetches_or_name_matches():
    candidate = capspace.Candidate(7, "Pavel", "Datsyuk", None, (2008,))
    session = Mock()

    outcome = capspace._fetch_profile(session, candidate)

    assert outcome.status == "no_nhl_id"
    session.get.assert_not_called()


def test_http_429_retry_after_then_success():
    candidate = capspace.Candidate(7, "Pavel", "Datsyuk", "8467514", (2008,))
    session = Mock()
    session.get.side_effect = [
        Mock(status_code=429, headers={"Retry-After": "3"}, text=""),
        Mock(status_code=200, headers={}, text=fixture("capspace_datsyuk.html")),
    ]
    with patch.object(capspace.time, "sleep") as sleep:
        outcome = capspace._fetch_profile(session, candidate)

    assert outcome.status == "succeeded"
    sleep.assert_called_once_with(3.0)
    assert session.get.call_count == 2


def test_http_timeout_and_retry_exhaustion_are_reported():
    candidate = capspace.Candidate(7, "Fixture", "Player", "123", (2008,))
    session = Mock()
    session.get.side_effect = requests.Timeout("slow")
    with patch.object(capspace.time, "sleep"):
        outcome = capspace._fetch_profile(session, candidate, max_attempts=2)
    assert outcome.status == "failed"
    assert outcome.error == "timeout"


def test_malformed_retry_after_uses_exponential_backoff():
    candidate = capspace.Candidate(7, "Fixture", "Player", "123", (2008,))
    session = Mock()
    session.get.side_effect = [
        Mock(status_code=429, headers={"Retry-After": "invalid"}, text=""),
        Mock(status_code=404, headers={}, text=""),
    ]

    with patch.object(capspace.time, "sleep") as sleep:
        outcome = capspace._fetch_profile(session, candidate, max_attempts=2)

    assert outcome.status == capspace.STATUS_NOT_FOUND
    sleep.assert_called_once_with(1)


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_retryable_server_errors_exhaust_without_mutation(status):
    candidate = capspace.Candidate(7, "Fixture", "Player", "123", (2008,))
    session = Mock()
    session.get.return_value = Mock(status_code=status, headers={}, text="")
    with patch.object(capspace.time, "sleep"):
        outcome = capspace._fetch_profile(session, candidate, max_attempts=2)
    assert outcome.status == "failed"
    assert outcome.error == f"HTTP {status}"
    assert session.get.call_count == 2


def test_json_contract_payload_is_supported():
    payload = {
        "props": {"pageProps": {"person": {"contracts": [{
            "id": "json-contract", "type": "Standard Contract", "value": "$1,000,000",
            "term": 1, "signingDate": "2020-07-01", "signingTeam": "AAA",
            "expiryStatus": "RFA", "details": [{"season": "2020-21", "capHit": "$1,000,000", "nhlSalary": "$900,000"}],
        }]}}}
    }
    html = '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(payload) + "</script>"

    contract = capspace.parse_capspace_page(html)[0]

    assert contract.external_id == "json-contract"
    assert contract.seasons[0].base_salary_cents == 90_000_000


def test_invalid_next_data_falls_back_to_rendered_contract_table():
    html = """
    <script id="__NEXT_DATA__" type="application/json">not-json</script>
    <article class="contract" data-contract-id="html-contract">
      <div>Total Value: $1,000,000 | Seasons: 1 | Signing Date: 2020-07-01</div>
      <table>
        <tr><td>Season</td><td>Cap Hit</td><td>NHL Salary</td></tr>
        <tr><td>2020-2021</td><td>$1,000,000</td><td>$1,000,000</td></tr>
      </table>
    </article>
    """

    contract = capspace.parse_capspace_page(html)[0]

    assert contract.external_id == "html-contract"
    assert contract.seasons[0].season_start_year == 2020


def test_json_date_plural_bonus_keys_and_identity_are_supported():
    payload = {
        "props": {"pageProps": {"player": {
            "nhlId": 8470281,
            "contracts": [{
                "type": "Standard Contract (Extension)",
                "value": "$72,000,000",
                "length": "13 years",
                "signingDate": "Dec. 3, 2009",
                "signingTeam": "Chicago Blackhawks",
                "expiryStatus": "UFA",
                "details": [{
                    "season": "2010-11",
                    "capHit": "$5,538,462",
                    "baseSalary": "$5,000,000",
                    "signingBonuses": "$3,000,000",
                    "performanceBonuses": "$25,000",
                }],
            }],
        }}}}
    html = '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(payload) + "</script>"

    contract = capspace.parse_capspace_page(html, expected_nhl_id="8470281")[0]

    assert contract.signed_on.isoformat() == "2009-12-03"
    assert contract.seasons[0].signing_bonus_cents == 300_000_000
    assert contract.seasons[0].performance_bonus_cents == 2_500_000


def test_embedded_page_identity_must_match_the_candidate_nhl_id():
    payload = {"props": {"pageProps": {"player": {"nhlId": 1, "contracts": []}}}}
    html = '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(payload) + "</script>"

    with pytest.raises(capspace.CapSpaceParseError, match="does not match"):
        capspace.parse_capspace_page(html, expected_nhl_id="2")


def test_capwages_name_lookup_requires_an_embedded_nhl_id():
    with pytest.raises(capspace.CapSpaceParseError, match="does not expose"):
        capspace.parse_capspace_page(
            capwages_html(None),
            expected_nhl_id="8470000",
            require_nhl_id=True,
        )


def test_legacy_capwages_identity_requires_name_slug_and_nhl_stats_overlap():
    candidate = capspace.Candidate(7, "Cory", "Stillman", "8458943", (2010,))
    payload = {
        "props": {"pageProps": {"player": {
            "name": "Stillman, Cory",
            "slug": "cory-stillman",
            "stats": [{
                "season": "2010-11",
                "league": "NHL",
                "gp": "65",
            }],
        }}}
    }
    html = '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(payload) + "</script>"

    assert capspace._capwages_identity_matches(
        html,
        candidate,
        "https://capwages.com/players/cory-stillman",
    )
    assert not capspace._capwages_identity_matches(
        html,
        capspace.Candidate(8, "Cory", "Stillman", "1", (2011,)),
        "https://capwages.com/players/cory-stillman",
    )


@pytest.mark.parametrize(
    "stats",
    [
        [{"season": "2010-11", "league": "AHL", "gp": "65"}],
        [{"season": "2010-11", "league": "NHL", "gp": "0"}],
        [{"season": "2010-11", "league": "NHL", "gp": "unknown"}],
    ],
)
def test_legacy_capwages_identity_requires_positive_nhl_games(stats):
    candidate = capspace.Candidate(7, "Cory", "Stillman", "8458943", (2010,))
    payload = {
        "props": {"pageProps": {"player": {
            "name": "Stillman, Cory",
            "slug": "cory-stillman",
            "stats": stats,
        }}}
    }
    html = '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(payload) + "</script>"

    assert not capspace._capwages_identity_matches(
        html,
        candidate,
        "https://capwages.com/players/cory-stillman",
    )


def test_capwages_fallback_tries_disambiguated_slug_and_preserves_source():
    candidate = capspace.Candidate(7, "Colin", "White", "8470000", (2010,))
    session = Mock()

    def response(url, timeout):
        if url.startswith("https://cap-space.com/"):
            return Mock(
                status_code=200,
                headers={},
                text="<h1>Contract History</h1>",
                url=url,
            )
        if url.endswith("/colin-white"):
            return Mock(status_code=200, headers={}, text=capwages_html(1), url=url)
        if url.endswith("/colin-white-1"):
            return Mock(
                status_code=200,
                headers={},
                text=capwages_html(8470000),
                url=url,
            )
        return Mock(status_code=404, headers={}, text="", url=url)

    session.get.side_effect = response

    outcome = capspace._fetch_profile_with_fallback(session, candidate)

    assert outcome.status == "succeeded"
    assert outcome.source_code == "capwages"
    assert outcome.fallback_attempted is True
    assert outcome.primary_status == "no_contracts"
    assert outcome.url.endswith("/colin-white-1")
    assert capspace._target_seasons_covered(outcome) == {2010}


def test_missing_capwages_base_slug_does_not_fan_out_numbered_requests():
    candidate = capspace.Candidate(7, "Absent", "Player", "8470000", (2010,))
    session = Mock()
    session.get.return_value = Mock(status_code=404, headers={}, text="")

    outcome = capspace._fetch_capwages_profile(session, candidate)

    assert outcome.status == "not_found"
    session.get.assert_called_once_with(
        "https://capwages.com/players/absent-player",
        timeout=30,
    )


def test_capwages_host_failure_stops_slug_fanout():
    candidate = capspace.Candidate(7, "Blocked", "Player", "8470000", (2010,))
    session = Mock()
    session.get.return_value = Mock(status_code=403, headers={}, text="")

    outcome = capspace._fetch_capwages_profile(session, candidate)

    assert outcome.status == "failed"
    assert outcome.error == "HTTP 403"
    assert session.get.call_count == 1


def test_capwages_success_parses_the_document_once():
    candidate = capspace.Candidate(7, "Fixture", "Player", "8470000", (2010,))
    session = Mock()
    session.get.return_value = Mock(
        status_code=200,
        headers={},
        text=capwages_html(8470000),
    )

    with patch.object(
        capspace._SourceDocument,
        "parse",
        wraps=capspace._SourceDocument.parse,
    ) as parse:
        outcome = capspace._fetch_capwages_profile(session, candidate)

    assert outcome.status == capspace.STATUS_SUCCEEDED
    assert parse.call_count == 1


def test_team_resolution_prefers_source_then_unique_stint():
    teams = {"det": 1, "detroit red wings": 1}
    stints = {2008: (2,), 2009: (2, 3)}

    assert capspace._resolve_team_id(teams, stints, 2008, "DET") == 1
    assert capspace._resolve_team_id(teams, stints, 2008, None) == 2
    assert capspace._resolve_team_id(teams, stints, 2009, None) is None
    assert capspace._resolve_team_id(teams, stints, 2010, None) is None


def test_profile_metrics_and_source_grouping_are_centralized():
    contract = capspace.parse_capspace_page(fixture("capspace_datsyuk.html"))[0]
    covered = capspace.Candidate(7, "Pavel", "Datsyuk", "8467514", (2008,))
    missing_id = capspace.Candidate(8, "No", "Identifier", None, (2008,))
    success = capspace.ProfileResult(
        covered,
        "https://capwages.com/players/pavel-datsyuk",
        capspace.STATUS_SUCCEEDED,
        (contract,),
        source_code=capspace.CAPWAGES_SOURCE,
        fallback_attempted=True,
        primary_status=capspace.STATUS_NO_CONTRACTS,
        fallback_status=capspace.STATUS_SUCCEEDED,
    )
    failure = capspace.ProfileResult(
        covered,
        "https://cap-space.com/person/nhl:8467514",
        capspace.STATUS_FAILED,
        fallback_attempted=True,
        fallback_status=capspace.STATUS_PARSE_FAILED,
    )

    metrics = capspace._profile_metrics([success, failure])
    grouped = capspace._source_records_by_code([covered, missing_id], [success])

    assert metrics["profiles_succeeded"] == 1
    assert metrics["profiles_with_target_coverage"] == 1
    assert metrics["profiles_failed"] == 1
    assert metrics["capwages_fallbacks_attempted"] == 2
    assert metrics["capwages_fallbacks_failed"] == 1
    assert grouped[capspace.CAPSPACE_SOURCE] == [
        (missing_id, {"status": capspace.STATUS_NO_NHL_ID})
    ]
    assert grouped[capspace.CAPWAGES_SOURCE][0][0] == covered
    assert grouped[capspace.CAPWAGES_SOURCE][0][1]["status"] == capspace.STATUS_SUCCEEDED


def test_normalize_contracts_preserves_typed_season_rows():
    contract = capspace.parse_capspace_page(fixture("capspace_datsyuk.html"))[0]

    normalized = capspace.normalize_contracts((contract,), "8467514")[0]

    assert normalized.external_id == "datsyuk-2007"
    assert normalized.seasons[0].season_start_year == 2008


def test_buyout_rows_are_ignored_after_real_salary_rows():
    html = """
    <article class="contract">
      <div>Total Value: $8,000,000 | Seasons: 2 | Signing Date: 2018-07-01</div>
      <table>
        <tr><td>Season</td><td>Cap Hit</td><td>NHL Salary</td></tr>
        <tr><td>2018-2019</td><td>$4,000,000</td><td>$3,000,000</td></tr>
        <tr><td>2019-2020</td><td>$4,000,000</td><td>$3,000,000</td></tr>
        <tr><td>Buyout Years</td></tr>
        <tr><td>2020-2021</td><td>$2,000,000</td><td>$0</td></tr>
      </table>
    </article>
    """

    contract = capspace.parse_capspace_page(html)[0]

    assert [row.season_start_year for row in contract.seasons] == [2018, 2019]


def test_named_cap_recapture_section_is_not_parsed_as_contract_seasons():
    html = """
    <article class="contract">
      <div>Total Value: $8,000,000 | Seasons: 2 | Signing Date: 2018-07-01</div>
      <table>
        <tr><td>Season</td><td>Cap Hit</td><td>NHL Salary</td></tr>
        <tr><td>2018-2019</td><td>$4,000,000</td><td>$3,000,000</td></tr>
        <tr><td>2019-2020</td><td>$4,000,000</td><td>$3,000,000</td></tr>
        <tr><td>Cap Recapture - Chicago Blackhawks</td></tr>
        <tr><td>Season</td><td>Cap Hit</td></tr>
        <tr><td>2019-2020</td><td>$4,000,000</td></tr>
        <tr><td>2020-2021</td><td>$2,000,000</td></tr>
      </table>
    </article>
    """

    contract = capspace.parse_capspace_page(html)[0]

    assert [row.season_start_year for row in contract.seasons] == [2018, 2019]


def test_no_recorded_contracts_is_not_a_markup_failure():
    assert capspace.parse_capspace_page("<h1>No recorded contracts</h1>") == ()


def test_one_bad_contract_block_does_not_discard_valid_contract_blocks():
    html = """
    <article class="contract">
      <div>Total Value: $1,000,000 | Seasons: 1</div>
      <table>
        <tr><td>Season</td><td>Cap Hit</td></tr>
        <tr><td>Buyout Years</td></tr>
      </table>
    </article>
    <article class="contract" data-contract-id="valid-contract">
      <div>Total Value: $2,000,000 | Seasons: 1 | Signing Date: 2020-07-01</div>
      <table>
        <tr><td>Season</td><td>Cap Hit</td><td>NHL Salary</td></tr>
        <tr><td>2020-2021</td><td>$2,000,000</td><td>$2,000,000</td></tr>
      </table>
    </article>
    """

    contracts = capspace.parse_capspace_page(html)

    assert len(contracts) == 1
    assert contracts[0].external_id == "valid-contract"


def test_candidate_query_uses_both_stat_tables_and_gap_filter():
    cursor = Mock()
    cursor.fetchall.return_value = [(1, "Pavel", "Datsyuk", "8467514", [2008, 2009])]

    candidates = capspace.select_candidates(cursor, first_season=2008, last_season=2025)

    sql = cursor.execute.call_args.args[0]
    assert "skater_season_stats" in sql
    assert "goalie_season_stats" in sql
    assert "NOT EXISTS" in sql
    assert candidates[0].nhl_id == "8467514"
    assert cursor.execute.call_args.args[1] == [2008, 2025, 2008, 2025]


def test_candidate_query_force_can_target_a_complete_player_without_name_matching():
    cursor = Mock()
    cursor.fetchall.return_value = []

    capspace.select_candidates(cursor, player_id=42, force=True)

    sql = cursor.execute.call_args.args[0]
    params = cursor.execute.call_args.args[1]
    assert "p.id = %s" in sql
    assert 42 in params
    assert "NOT EXISTS" not in sql


def test_targeted_player_still_selects_only_missing_seasons_without_force():
    cursor = Mock()
    cursor.fetchall.return_value = []

    capspace.select_candidates(cursor, player_id=42)

    sql = cursor.execute.call_args.args[0]
    assert "p.id = %s" in sql
    assert "NOT EXISTS" in sql


@pytest.mark.parametrize(
    "options",
    [
        {"workers": 0},
        {"workers": capspace.MAX_WORKERS + 1},
        {"batch_size": 0},
        {"batch_size": capspace.MAX_BATCH_SIZE + 1},
    ],
)
def test_run_rejects_unsafe_worker_and_batch_bounds(options):
    with pytest.raises(ValueError):
        capspace._run(Mock(), dry_run=True, **options)


def test_run_returns_complete_empty_summary_without_fetching(monkeypatch):
    monkeypatch.setattr(
        capspace,
        "_candidate_snapshot",
        lambda **_: ([], {"candidate_player_seasons": 0, "candidate_players": 0}),
    )
    fetch = Mock()
    monkeypatch.setattr(capspace, "_fetch_profiles", fetch)

    summary = capspace._run(Mock(), dry_run=True)

    assert summary == {
        "candidate_player_seasons": 0,
        "candidate_players": 0,
        "players_without_nhl_ids": 0,
        "profiles_requested": 0,
        "records_read": 0,
        "records_created": 0,
        "records_updated": 0,
        "records_skipped": 0,
        "remaining_uncovered_player_seasons": 0,
    }
    fetch.assert_not_called()
