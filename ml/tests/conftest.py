from __future__ import annotations

import pandas as pd
import pytest


@pytest.fixture
def player_seasons() -> pd.DataFrame:
    rows = []
    for season in range(2021, 2026):
        for player_id, position, multiplier in ((1, "C", 1.0), (2, "D", 0.8), (3, "LW", 1.2), (4, "RW", 0.6)):
            games = 22 + player_id
            toi = (3600 + player_id * 600) * multiplier
            goals = season - 2018 + player_id
            rows.append({
                "player_id": player_id, "player_name": f"Player {player_id}", "season": season, "position": position,
                "games_played": games, "goals": goals, "assists": goals + 2, "points": goals * 2 + 2,
                "ice_time_seconds": toi, "game_score": goals * 1.5, "individual_expected_goals": goals - 0.5,
                "individual_shots_on_goal": goals * 3, "individual_unblocked_attempts": goals * 5,
                "individual_primary_assists": 2, "individual_secondary_assists": 1, "takeaways": 8,
                "giveaways": 4, "shots_blocked": 3, "penalties": 2, "penalties_drawn": 3,
                "on_ice_expected_goals_pct": 0.51 + player_id / 100, "offensive_zone_shift_starts": 10,
                "defensive_zone_shift_starts": 8, "neutral_zone_shift_starts": 2,
            })
    rows[0]["goals"] = None
    rows[1]["ice_time_seconds"] = 0
    return pd.DataFrame(rows)
