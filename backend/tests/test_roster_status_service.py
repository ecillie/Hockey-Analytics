from datetime import date
import unittest

from app.ScriptingFiles.FullDataScript.roster_status.ahl_roster_service import (
    AhlRosterService,
)
from app.ScriptingFiles.FullDataScript.roster_status.nhl_roster_service import (
    NhlRosterService,
)
from app.ScriptingFiles.FullDataScript.roster_status.roster_models import (
    ExternalRosterPlayer,
    FetchResult,
    RosterStatus,
    StoredPlayer,
)
from app.ScriptingFiles.FullDataScript.roster_status.roster_status_service import (
    RosterStatusService,
)


class FakeRepository:
    def __init__(self, players, ltir_player_ids=None):
        self.players = players
        self.ltir_player_ids = ltir_player_ids or set()
        self.updates = {}
        self.ahl_mappings = []

    def load_players(self):
        return self.players

    def load_active_ltir_player_ids(self, as_of):
        return self.ltir_player_ids

    def bulk_update_statuses(self, updates):
        self.updates = updates

    def save_ahl_external_ids(self, matches):
        self.ahl_mappings = list(matches)


class FakeRosterService:
    def __init__(self, result):
        self.result = result

    def fetch_current_rosters(self):
        return self.result


class FakeHttpClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get_json(self, url, params=None):
        self.calls.append((url, params))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def stored_player(
    player_id=1,
    status=RosterStatus.UNKNOWN,
    nhl_id="8478402",
    ahl_id=None,
    name=("Connor", "McDavid"),
    birth_date=date(1997, 1, 13),
):
    return StoredPlayer(
        id=player_id,
        first_name=name[0],
        last_name=name[1],
        birth_date=birth_date,
        roster_status=status,
        nhl_external_id=nhl_id,
        ahl_external_id=ahl_id,
    )


def nhl_result(*player_ids, complete=True):
    return FetchResult(
        items={
            player_id: ExternalRosterPlayer(player_id, "NHL Player")
            for player_id in player_ids
        },
        complete=complete,
        errors=() if complete else ("NHL failed",),
    )


def ahl_result(*players, complete=True):
    return FetchResult(
        items=list(players),
        complete=complete,
        errors=() if complete else ("AHL failed",),
    )


class RosterStatusServiceTests(unittest.TestCase):
    def sync(self, player, nhl, ahl, ltir=None):
        repository = FakeRepository([player], ltir)
        summary = RosterStatusService(
            repository,
            FakeRosterService(nhl),
            FakeRosterService(ahl),
        ).sync(date(2026, 9, 6))
        return repository, summary

    def test_nhl_roster_player_is_active_by_id(self):
        player = stored_player(name=("Different", "Name"))
        repository, _ = self.sync(
            player,
            nhl_result("8478402"),
            ahl_result(),
        )
        self.assertEqual(repository.updates[player.id], RosterStatus.ACTIVE)

    def test_ahl_roster_player_is_minors_by_name_and_dob(self):
        player = stored_player(name=("Kaapo", "Kahkonen"), birth_date=date(1996, 8, 16))
        ahl_player = ExternalRosterPlayer(
            "7179",
            "Kaapo Kähkönen",
            date(1996, 8, 16),
        )
        repository, _ = self.sync(player, nhl_result(), ahl_result(ahl_player))
        self.assertEqual(repository.updates[player.id], RosterStatus.MINORS)
        self.assertEqual(repository.ahl_mappings, [(player.id, "7179", "Kaapo Kähkönen")])

    def test_existing_ahl_id_is_preferred_over_name(self):
        player = stored_player(ahl_id="7179", name=("Old", "Name"))
        ahl_player = ExternalRosterPlayer("7179", "New Name", date(1990, 1, 1))
        repository, _ = self.sync(player, nhl_result(), ahl_result(ahl_player))
        self.assertEqual(repository.updates[player.id], RosterStatus.MINORS)

    def test_ltir_override_beats_nhl_roster(self):
        player = stored_player()
        repository, _ = self.sync(
            player,
            nhl_result("8478402"),
            ahl_result(),
            {player.id},
        )
        self.assertEqual(repository.updates[player.id], RosterStatus.LTIR)

    def test_ltir_override_beats_ahl_roster(self):
        player = stored_player(ahl_id="7179")
        ahl_player = ExternalRosterPlayer("7179", "AHL Player")
        repository, _ = self.sync(
            player,
            nhl_result(),
            ahl_result(ahl_player),
            {player.id},
        )
        self.assertEqual(repository.updates[player.id], RosterStatus.LTIR)

    def test_player_found_nowhere_is_unknown(self):
        player = stored_player(status=RosterStatus.ACTIVE)
        repository, _ = self.sync(player, nhl_result(), ahl_result())
        self.assertEqual(repository.updates[player.id], RosterStatus.UNKNOWN)

    def test_nhl_failure_preserves_existing_status(self):
        player = stored_player(status=RosterStatus.MINORS)
        repository, summary = self.sync(
            player,
            nhl_result(complete=False),
            ahl_result(),
        )
        self.assertNotIn(player.id, repository.updates)
        self.assertEqual(summary.preserved_count, 1)

    def test_ahl_failure_does_not_create_unknown(self):
        player = stored_player(status=RosterStatus.MINORS)
        repository, summary = self.sync(
            player,
            nhl_result(),
            ahl_result(complete=False),
        )
        self.assertNotIn(player.id, repository.updates)
        self.assertEqual(summary.preserved_count, 1)

    def test_ambiguous_name_and_dob_does_not_match_ahl(self):
        first = stored_player(player_id=1, nhl_id="1", name=("Same", "Player"))
        second = stored_player(player_id=2, nhl_id="2", name=("Same", "Player"))
        repository = FakeRepository([first, second])
        ahl_player = ExternalRosterPlayer("99", "Same Player", first.birth_date)
        RosterStatusService(
            repository,
            FakeRosterService(nhl_result()),
            FakeRosterService(ahl_result(ahl_player)),
        ).sync()
        self.assertEqual(repository.updates[1], RosterStatus.UNKNOWN)
        self.assertEqual(repository.updates[2], RosterStatus.UNKNOWN)
        self.assertEqual(repository.ahl_mappings, [])


class RosterFeedClientTests(unittest.TestCase):
    def test_nhl_service_collects_players_by_nhl_id(self):
        http = FakeHttpClient(
            [
                {
                    "standings": [
                        {"teamAbbrev": {"default": "EDM"}},
                        {"teamAbbrev": {"default": "TOR"}},
                    ]
                },
                {
                    "forwards": [
                        {
                            "id": 8478402,
                            "firstName": {"default": "Connor"},
                            "lastName": {"default": "McDavid"},
                        }
                    ],
                    "defensemen": [],
                    "goalies": [],
                },
                {"forwards": [], "defensemen": [], "goalies": []},
            ]
        )
        result = NhlRosterService(http).fetch_current_rosters()
        self.assertTrue(result.complete)
        self.assertIn("8478402", result.items)
        self.assertEqual(result.items["8478402"].full_name, "Connor McDavid")

    def test_ahl_service_reads_public_feed_player_id_name_and_dob(self):
        http = FakeHttpClient(
            [
                {
                    "current_season_id": "90",
                    "current_league_id": "4",
                    "teamsNoAll": [{"id": "415", "name": "Laval Rocket"}],
                },
                {
                    "roster": [
                        {
                            "sections": [
                                {
                                    "data": [
                                        {
                                            "row": {
                                                "player_id": "7179",
                                                "name": "Kaapo Kähkönen",
                                                "birthdate": "1996-08-16",
                                            }
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                },
            ]
        )
        result = AhlRosterService(http_client=http).fetch_current_rosters()
        self.assertTrue(result.complete)
        self.assertEqual(result.items[0].external_id, "7179")
        self.assertEqual(result.items[0].birth_date, date(1996, 8, 16))
        roster_params = http.calls[1][1]
        self.assertEqual(roster_params["view"], "roster")
        self.assertNotIn("rosterstatus", roster_params)

    def test_ahl_partial_failure_keeps_positive_results_but_marks_incomplete(self):
        http = FakeHttpClient(
            [
                {
                    "current_season_id": "90",
                    "current_league_id": "4",
                    "teamsNoAll": [{"id": "1"}, {"id": "2"}],
                },
                {
                    "roster": [
                        {
                            "sections": [
                                {
                                    "data": [
                                        {
                                            "row": {
                                                "player_id": "10",
                                                "name": "Found Player",
                                                "birthdate": "2000-01-01",
                                            }
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                },
                TimeoutError("feed timeout"),
            ]
        )
        result = AhlRosterService(http_client=http).fetch_current_rosters()
        self.assertFalse(result.complete)
        self.assertEqual([player.external_id for player in result.items], ["10"])
        self.assertEqual(len(result.errors), 1)


if __name__ == "__main__":
    unittest.main()
