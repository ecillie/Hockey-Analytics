"""PostgreSQL queries for the read-only public API.

The summary CTE deliberately chooses TOTAL rows when present and otherwise
aggregates team stints. That rule prevents traded players from being counted
twice while still supporting seasons whose source has no TOTAL row.
"""

SUMMARY_CTES = r"""
WITH team_choice AS (
    SELECT DISTINCT ON (pts.player_id, pts.season_start_year)
        pts.player_id, pts.season_start_year, t.id team_id,
        t.nhl_team_id, t.abbreviation, t.name team_name, t.city team_city,
        t.active team_active
    FROM player_team_stints pts
    JOIN teams t ON t.id = pts.team_id
    WHERE pts.season_start_year = :season
    ORDER BY pts.player_id, pts.season_start_year,
             (pts.departed_on IS NULL) DESC, pts.departed_on DESC NULLS LAST,
             pts.joined_on DESC NULLS LAST, pts.id DESC
),
traditional AS (
    SELECT s.player_id,
        SUM(s.games_played)::int games_played,
        SUM(s.goals)::int goals, SUM(s.assists)::int assists,
        SUM(s.points)::int points, SUM(s.plus_minus)::int plus_minus,
        SUM(s.penalty_minutes)::int penalty_minutes,
        SUM(s.power_play_goals)::int power_play_goals,
        SUM(s.power_play_points)::int power_play_points,
        SUM(s.short_handed_goals)::int short_handed_goals,
        SUM(s.shots)::int shots,
        CASE WHEN SUM(s.shots) > 0 THEN SUM(s.goals)::float / SUM(s.shots) END shooting_percentage
    FROM skater_season_stats s
    WHERE s.season_start_year = :season AND s.game_type = 2
      AND (s.stat_scope = 'TOTAL' OR NOT EXISTS (
          SELECT 1 FROM skater_season_stats total
          WHERE total.player_id = s.player_id
            AND total.season_start_year = s.season_start_year
            AND total.game_type = s.game_type AND total.stat_scope = 'TOTAL'))
    GROUP BY s.player_id
),
advanced AS (
    SELECT a.player_id,
        SUM(a.ice_time_seconds)::float ice_time_seconds,
        SUM(a.shifts)::int shifts, SUM(a.game_score)::float game_score,
        SUM(a.individual_expected_goals)::float individual_expected_goals,
        SUM(a.takeaways)::int takeaways, SUM(a.giveaways)::int giveaways,
        SUM(a.shots_blocked)::int shots_blocked,
        SUM(a.penalties)::int penalties, SUM(a.penalties_drawn)::int penalties_drawn,
        CASE WHEN SUM(a.ice_time_seconds) > 0
             THEN SUM(a.game_score) * 3600.0 / SUM(a.ice_time_seconds) END game_score_per_60,
        CASE WHEN SUM(a.ice_time_seconds) > 0
             THEN SUM(a.individual_expected_goals) * 3600.0 / SUM(a.ice_time_seconds) END expected_goals_per_60,
        CASE WHEN SUM(a.ice_time_seconds) > 0
             THEN SUM(a.on_ice_expected_goals_pct * a.ice_time_seconds)
                  / SUM(a.ice_time_seconds) END on_ice_expected_goals_pct
    FROM skater_advanced_season_stats a
    WHERE a.season_start_year = :season AND a.game_type = 2 AND a.situation = 'all'
      AND (a.stat_scope = 'TOTAL' OR NOT EXISTS (
          SELECT 1 FROM skater_advanced_season_stats total
          WHERE total.player_id = a.player_id
            AND total.season_start_year = a.season_start_year
            AND total.game_type = a.game_type AND total.situation = a.situation
            AND total.stat_scope = 'TOTAL'))
    GROUP BY a.player_id
),
goalie AS (
    SELECT g.player_id, SUM(g.games_played)::int games_played
    FROM goalie_season_stats g
    WHERE g.season_start_year = :season AND g.game_type = 2
      AND (g.stat_scope = 'TOTAL' OR NOT EXISTS (
          SELECT 1 FROM goalie_season_stats total
          WHERE total.player_id = g.player_id
            AND total.season_start_year = g.season_start_year
            AND total.game_type = g.game_type AND total.stat_scope = 'TOTAL'))
    GROUP BY g.player_id
),
eligible AS (
    SELECT a.player_id,
        CASE WHEN p.primary_position = 'D' THEN 'defense' ELSE 'forward' END position_group,
        a.game_score_per_60,
        a.ice_time_seconds / NULLIF(tr.games_played, 0) toi_per_game
    FROM advanced a JOIN players p ON p.id = a.player_id
    LEFT JOIN traditional tr ON tr.player_id = a.player_id
    WHERE p.primary_position <> 'G' AND tr.games_played >= 20 AND a.ice_time_seconds > 0
),
thresholds AS (
    SELECT position_group,
        percentile_cont(0.20) WITHIN GROUP (ORDER BY toi_per_game) toi_threshold
    FROM eligible GROUP BY position_group
),
replacement AS (
    SELECT e.position_group,
        percentile_cont(0.50) WITHIN GROUP (ORDER BY e.game_score_per_60) replacement_gs60
    FROM eligible e JOIN thresholds t USING (position_group)
    WHERE e.toi_per_game <= t.toi_threshold
    GROUP BY e.position_group
),
active_model AS (
    SELECT version FROM model_versions
    WHERE active AND model_type IN ('skater_value', 'skater-value')
    ORDER BY created_at DESC LIMIT 1
),
projection AS (
    SELECT DISTINCT ON (pr.player_id) pr.player_id,
        NULLIF(pr.input_features ->> 'predicted_hockey_value', '')::float projected_hockey_value,
        mv.version model_version
    FROM predictions pr JOIN model_versions mv ON mv.id = pr.model_version_id
    WHERE pr.target_season = :season + 1
      AND pr.input_features ? 'predicted_hockey_value'
    ORDER BY pr.player_id, pr.created_at DESC
),
cap_hit AS (
    SELECT c.player_id, MAX(cs.cap_hit_cents)::bigint cap_hit_cents
    FROM contracts c JOIN contract_seasons cs ON cs.contract_id = c.id
    WHERE cs.season_start_year = :season GROUP BY c.player_id
),
summary AS (
    SELECT p.id, p.first_name, p.last_name,
        CONCAT_WS(' ', p.first_name, p.last_name) full_name,
        p.birth_date,
        CASE WHEN p.birth_date IS NULL THEN NULL
             ELSE EXTRACT(YEAR FROM age(CURRENT_DATE, p.birth_date))::int END age,
        p.primary_position, p.shoots_catches, p.nationality, p.active,
        p.roster_status::text roster_status,
        tc.team_id, tc.nhl_team_id, tc.abbreviation, tc.team_name, tc.team_city, tc.team_active,
        CAST(:season AS int) season,
        COALESCE(tr.games_played, g.games_played) games_played,
        tr.goals, tr.assists, tr.points, tr.plus_minus, tr.penalty_minutes,
        tr.power_play_goals, tr.power_play_points, tr.short_handed_goals,
        tr.shots, tr.shooting_percentage,
        a.ice_time_seconds, a.shifts, a.game_score, a.game_score_per_60,
        a.individual_expected_goals, a.expected_goals_per_60,
        a.on_ice_expected_goals_pct, a.takeaways, a.giveaways,
        a.shots_blocked, a.penalties, a.penalties_drawn,
        CASE WHEN a.game_score_per_60 IS NOT NULL AND r.replacement_gs60 IS NOT NULL
             THEN (a.game_score_per_60 - r.replacement_gs60) * a.ice_time_seconds / 3600.0 END hockey_value,
        pj.projected_hockey_value,
        CASE WHEN a.game_score_per_60 IS NOT NULL AND r.replacement_gs60 IS NOT NULL
             THEN a.game_score_per_60 - r.replacement_gs60 END gs60_above_replacement,
        COALESCE(pj.model_version, (SELECT version FROM active_model),
                 CASE WHEN a.game_score_per_60 IS NOT NULL THEN 'replacement-level-v1' END) model_version,
        ch.cap_hit_cents
    FROM players p
    LEFT JOIN team_choice tc ON tc.player_id = p.id
    LEFT JOIN traditional tr ON tr.player_id = p.id
    LEFT JOIN advanced a ON a.player_id = p.id
    LEFT JOIN goalie g ON g.player_id = p.id
    LEFT JOIN replacement r ON r.position_group =
        CASE WHEN p.primary_position = 'D' THEN 'defense' ELSE 'forward' END
    LEFT JOIN projection pj ON pj.player_id = p.id
    LEFT JOIN cap_hit ch ON ch.player_id = p.id
)
"""


PLAYER_IDENTITY_SQL = r"""
SELECT p.id, p.first_name, p.last_name, CONCAT_WS(' ', p.first_name, p.last_name) full_name,
    p.birth_date,
    CASE WHEN p.birth_date IS NULL THEN NULL
         ELSE EXTRACT(YEAR FROM age(CURRENT_DATE, p.birth_date))::int END age,
    p.primary_position, p.shoots_catches, p.nationality, p.active,
    p.roster_status::text roster_status,
    t.id team_id, t.nhl_team_id, t.abbreviation, t.name team_name, t.city team_city, t.active team_active
FROM players p
LEFT JOIN LATERAL (
    SELECT pts.team_id FROM player_team_stints pts
    WHERE pts.player_id = p.id
    ORDER BY pts.season_start_year DESC, (pts.departed_on IS NULL) DESC,
             pts.departed_on DESC NULLS LAST, pts.id DESC LIMIT 1
) current_stint ON true
LEFT JOIN teams t ON t.id = current_stint.team_id
WHERE p.id = :player_id
"""


TEAM_SQL = """
SELECT id, nhl_team_id, abbreviation, name team_name, city team_city, active team_active
FROM teams WHERE id = :team_id
"""


CONTRACT_SQL = r"""
SELECT c.id, c.player_id, c.signed_on, c.start_season, c.end_season, c.term_years,
    c.contract_type, c.expiry_status, c.total_value_cents, c.average_value_cents,
    c.is_entry_level,
    st.id signing_team_id, st.nhl_team_id signing_nhl_team_id,
    st.abbreviation signing_abbreviation, st.name signing_team_name,
    st.city signing_team_city, st.active signing_team_active
FROM contracts c LEFT JOIN teams st ON st.id = c.signing_team_id
WHERE c.player_id = :player_id
ORDER BY (c.start_season <= :current_season AND c.end_season >= :current_season) DESC,
         c.end_season DESC, c.start_season DESC, c.id DESC LIMIT 1
"""


CONTRACT_SEASONS_SQL = r"""
SELECT cs.season_start_year, cs.base_salary_cents, cs.signing_bonus_cents,
    cs.performance_bonus_cents, cs.total_cash_cents, cs.cap_hit_cents,
    cs.cap_percentage, cs.is_slide,
    t.id team_id, t.nhl_team_id, t.abbreviation, t.name team_name,
    t.city team_city, t.active team_active
FROM contract_seasons cs LEFT JOIN teams t ON t.id = cs.owning_team_id
WHERE cs.contract_id = :contract_id ORDER BY cs.season_start_year
"""


TEAM_SQL = r"""
SELECT id, nhl_team_id, abbreviation, name team_name, city team_city,
       active team_active
FROM teams WHERE id = :team_id
"""


PLAYER_IDENTITY_SQL = r"""
SELECT p.id, p.first_name, p.last_name,
    CONCAT_WS(' ', p.first_name, p.last_name) full_name, p.birth_date,
    CASE WHEN p.birth_date IS NULL THEN NULL
         ELSE EXTRACT(YEAR FROM age(CURRENT_DATE, p.birth_date))::int END age,
    p.primary_position, p.shoots_catches, p.nationality, p.active,
    p.roster_status::text roster_status,
    t.id team_id, t.nhl_team_id, t.abbreviation, t.name team_name,
    t.city team_city, t.active team_active
FROM players p
LEFT JOIN LATERAL (
    SELECT pts.team_id FROM player_team_stints pts
    WHERE pts.player_id = p.id
    ORDER BY pts.season_start_year DESC, (pts.departed_on IS NULL) DESC,
             pts.departed_on DESC NULLS LAST, pts.joined_on DESC NULLS LAST,
             pts.id DESC LIMIT 1
) latest ON true
LEFT JOIN teams t ON t.id = latest.team_id
WHERE p.id = :player_id
"""


CONTRACT_SQL = r"""
SELECT c.id, c.player_id, c.signed_on, c.start_season, c.end_season,
    c.term_years, c.contract_type, c.expiry_status, c.total_value_cents,
    c.average_value_cents, c.is_entry_level,
    t.id signing_team_id, t.nhl_team_id signing_nhl_team_id,
    t.abbreviation signing_abbreviation, t.name signing_team_name,
    t.city signing_team_city, t.active signing_team_active
FROM contracts c LEFT JOIN teams t ON t.id = c.signing_team_id
WHERE c.player_id = :player_id
ORDER BY (:current_season BETWEEN c.start_season AND c.end_season) DESC,
         c.end_season DESC, c.signed_on DESC NULLS LAST, c.id DESC
LIMIT 1
"""
