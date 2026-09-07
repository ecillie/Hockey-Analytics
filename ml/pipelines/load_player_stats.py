from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database import engine  # noqa: E402


PLAYER_SEASON_QUERY = text("""
WITH basic_total AS (
    SELECT
        player_id,
        season_start_year,
        games_played,
        goals,
        assists,
        points,
        plus_minus,
        penalty_minutes,
        power_play_goals,
        power_play_points,
        short_handed_goals,
        shots,
        shooting_percentage
    FROM (
        SELECT
            s.*,
            ROW_NUMBER() OVER (
                PARTITION BY s.player_id, s.season_start_year
                ORDER BY s.updated_at DESC
            ) AS rn
        FROM skater_season_stats s
        WHERE s.game_type = 2
          AND s.stat_scope = 'TOTAL'
    ) x
    WHERE rn = 1
),

basic_team AS (
    SELECT
        player_id,
        season_start_year,

        SUM(COALESCE(games_played, 0)) AS games_played,
        SUM(COALESCE(goals, 0)) AS goals,
        SUM(COALESCE(assists, 0)) AS assists,
        SUM(COALESCE(points, 0)) AS points,
        SUM(COALESCE(plus_minus, 0)) AS plus_minus,
        SUM(COALESCE(penalty_minutes, 0)) AS penalty_minutes,
        SUM(COALESCE(power_play_goals, 0)) AS power_play_goals,
        SUM(COALESCE(power_play_points, 0)) AS power_play_points,
        SUM(COALESCE(short_handed_goals, 0)) AS short_handed_goals,
        SUM(COALESCE(shots, 0)) AS shots,

        CASE
            WHEN SUM(COALESCE(shots, 0)) > 0
            THEN SUM(COALESCE(goals, 0))::DOUBLE PRECISION
                 / SUM(COALESCE(shots, 0))
            ELSE NULL
        END AS shooting_percentage

    FROM skater_season_stats
    WHERE game_type = 2
      AND stat_scope = 'TEAM'

    GROUP BY
        player_id,
        season_start_year
),

basic AS (
    SELECT * FROM basic_total

    UNION ALL

    SELECT bt.*
    FROM basic_team bt
    WHERE NOT EXISTS (
        SELECT 1
        FROM basic_total btot
        WHERE btot.player_id = bt.player_id
          AND btot.season_start_year = bt.season_start_year
    )
),

advanced_total AS (
    SELECT
        player_id,
        season_start_year,
        ice_time_seconds,
        shifts,
        game_score,
        individual_points,
        individual_goals,
        individual_primary_assists,
        individual_secondary_assists,
        individual_expected_goals,
        individual_shots_on_goal,
        individual_unblocked_attempts,
        on_ice_expected_goals_pct,
        shots_blocked,
        takeaways,
        giveaways,
        penalties,
        penalties_drawn,
        offensive_zone_shift_starts,
        defensive_zone_shift_starts,
        neutral_zone_shift_starts
    FROM (
        SELECT
            a.*,
            ROW_NUMBER() OVER (
                PARTITION BY a.player_id, a.season_start_year
                ORDER BY a.updated_at DESC
            ) AS rn
        FROM skater_advanced_season_stats a
        WHERE a.game_type = 2
          AND a.stat_scope = 'TOTAL'
          AND LOWER(a.situation) = 'all'
    ) x
    WHERE rn = 1
),

advanced_team AS (
    SELECT
        player_id,
        season_start_year,

        SUM(COALESCE(ice_time_seconds, 0)) AS ice_time_seconds,
        SUM(COALESCE(shifts, 0)) AS shifts,
        SUM(COALESCE(game_score, 0)) AS game_score,
        SUM(COALESCE(individual_points, 0)) AS individual_points,
        SUM(COALESCE(individual_goals, 0)) AS individual_goals,
        SUM(COALESCE(individual_primary_assists, 0))
            AS individual_primary_assists,
        SUM(COALESCE(individual_secondary_assists, 0))
            AS individual_secondary_assists,
        SUM(COALESCE(individual_expected_goals, 0))
            AS individual_expected_goals,
        SUM(COALESCE(individual_shots_on_goal, 0))
            AS individual_shots_on_goal,
        SUM(COALESCE(individual_unblocked_attempts, 0))
            AS individual_unblocked_attempts,

        CASE
            WHEN SUM(COALESCE(ice_time_seconds, 0)) > 0
            THEN
                SUM(
                    COALESCE(on_ice_expected_goals_pct, 0)
                    * COALESCE(ice_time_seconds, 0)
                )
                / SUM(COALESCE(ice_time_seconds, 0))
            ELSE NULL
        END AS on_ice_expected_goals_pct,

        SUM(COALESCE(shots_blocked, 0)) AS shots_blocked,
        SUM(COALESCE(takeaways, 0)) AS takeaways,
        SUM(COALESCE(giveaways, 0)) AS giveaways,
        SUM(COALESCE(penalties, 0)) AS penalties,
        SUM(COALESCE(penalties_drawn, 0)) AS penalties_drawn,

        SUM(COALESCE(offensive_zone_shift_starts, 0))
            AS offensive_zone_shift_starts,
        SUM(COALESCE(defensive_zone_shift_starts, 0))
            AS defensive_zone_shift_starts,
        SUM(COALESCE(neutral_zone_shift_starts, 0))
            AS neutral_zone_shift_starts

    FROM skater_advanced_season_stats

    WHERE game_type = 2
      AND stat_scope = 'TEAM'
      AND LOWER(situation) = 'all'

    GROUP BY
        player_id,
        season_start_year
),

advanced AS (
    SELECT * FROM advanced_total

    UNION ALL

    SELECT at.*
    FROM advanced_team at
    WHERE NOT EXISTS (
        SELECT 1
        FROM advanced_total atot
        WHERE atot.player_id = at.player_id
          AND atot.season_start_year = at.season_start_year
    )
)

SELECT
    p.id AS player_id,
    p.first_name,
    p.last_name,

    CONCAT(
        p.first_name,
        ' ',
        p.last_name
    ) AS player_name,

    p.birth_date,
    p.primary_position AS position,

    b.season_start_year AS season,

    CASE
        WHEN p.birth_date IS NOT NULL THEN
            EXTRACT(
                YEAR FROM AGE(
                    MAKE_DATE(
                        b.season_start_year,
                        10,
                        1
                    ),
                    p.birth_date
                )
            )::INTEGER
        ELSE NULL
    END AS age,

    b.games_played,
    b.goals,
    b.assists,
    b.points,
    b.plus_minus,
    b.penalty_minutes,
    b.power_play_goals,
    b.power_play_points,
    b.short_handed_goals,
    b.shots,
    b.shooting_percentage,

    a.ice_time_seconds,
    a.shifts,
    a.game_score,
    a.individual_points,
    a.individual_goals,
    a.individual_primary_assists,
    a.individual_secondary_assists,
    a.individual_expected_goals,
    a.individual_shots_on_goal,
    a.individual_unblocked_attempts,
    a.on_ice_expected_goals_pct,
    a.shots_blocked,
    a.takeaways,
    a.giveaways,
    a.penalties,
    a.penalties_drawn,
    a.offensive_zone_shift_starts,
    a.defensive_zone_shift_starts,
    a.neutral_zone_shift_starts

FROM basic b

JOIN players p
    ON p.id = b.player_id

LEFT JOIN advanced a
    ON a.player_id = b.player_id
   AND a.season_start_year = b.season_start_year

WHERE COALESCE(p.primary_position, '') <> 'G'

ORDER BY
    b.season_start_year,
    p.last_name,
    p.first_name;
""")


def load_player_stats(
    min_games: int = 1,
) -> pd.DataFrame:
    """
    Load one regular-season row per skater-season.

    TOTAL rows are preferred when available.
    Otherwise TEAM rows are combined into full-season totals.

    Contract data is intentionally excluded.
    """

    with engine.connect() as connection:
        df = pd.read_sql(
            PLAYER_SEASON_QUERY,
            connection,
        )

    if min_games > 1:
        df = df[
            df["games_played"].fillna(0) >= min_games
        ].copy()

    return df.reset_index(drop=True)


def print_diagnostics(
    df: pd.DataFrame,
) -> None:
    print("\n=== SKATER ML DATA PIPELINE ===")
    print(f"Rows: {len(df):,}")

    if df.empty:
        print("No player-season rows found.")
        return

    print(
        f"Players: "
        f"{df['player_id'].nunique():,}"
    )

    print(
        f"Seasons: "
        f"{df['season'].min()} - "
        f"{df['season'].max()}"
    )

    print(f"Columns: {len(df.columns)}")

    duplicate_count = df.duplicated(
        subset=[
            "player_id",
            "season",
        ]
    ).sum()

    print(
        f"Duplicate player-seasons: "
        f"{duplicate_count:,}"
    )

    advanced_available = (
        df["ice_time_seconds"]
        .notna()
        .sum()
    )

    print(
        "Rows with advanced stats: "
        f"{advanced_available:,} / "
        f"{len(df):,}"
    )

    print("\nRows by season:")

    print(
        df.groupby("season")
        .size()
        .sort_index()
        .to_string()
    )

    print("\nSample:")

    sample_columns = [
        "player_id",
        "player_name",
        "season",
        "position",
        "age",
        "games_played",
        "goals",
        "assists",
        "points",
        "individual_expected_goals",
        "on_ice_expected_goals_pct",
        "game_score",
    ]

    print(
        df[sample_columns]
        .head(15)
        .to_string(index=False)
    )


if __name__ == "__main__":
    player_stats = load_player_stats()
    print_diagnostics(player_stats)