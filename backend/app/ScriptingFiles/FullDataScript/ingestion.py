"""Schema-native ingestion for the TradeValue data sources.

The older scripts in this directory target a retired ORM schema.  This module
loads the same sources directly into ``backend/database/schema.sql`` and keeps
each source stage transactional and repeatable.
"""

from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import logging
from pathlib import Path
import re
from typing import Any, Iterable
import unicodedata

from psycopg2.extras import Json, execute_values
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.database import database_transaction, init_db


LOGGER = logging.getLogger(__name__)
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
HEADERS = {
    "User-Agent": "TradeValue/1.0 (NHL analytics data ingestion)",
    "Accept": "application/json,text/csv,text/html",
}
MONEYPUCK_FILES = {
    "skater": DATA_DIR / "skater advanced" / "skaters_2008_to_2024.csv",
    "goalie": DATA_DIR / "goalie_advanced" / "goalies_2008_to_2024.csv",
}
MONEYPUCK_URLS = {
    "skater": "https://moneypuck.com/moneypuck/playerData/seasonSummary/2025/regular/skaters.csv",
    "goalie": "https://moneypuck.com/moneypuck/playerData/seasonSummary/2025/regular/goalies.csv",
}


def http_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=4,
        backoff_factor=0.6,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        respect_retry_after_header=True,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update(HEADERS)
    return session


def _default(value: Any) -> Any:
    if isinstance(value, dict):
        return value.get("default") or next(iter(value.values()), None)
    return value


def _split_name(full_name: str) -> tuple[str, str]:
    name = " ".join((full_name or "").strip().split())
    if "," in name:
        last, first = (part.strip() for part in name.split(",", 1))
        return first, last
    first, separator, last = name.partition(" ")
    return first, last if separator else "Unknown"


def _position(value: Any, goalie: bool = False) -> str | None:
    if goalie:
        return "G"
    text = str(value or "").upper().split(",", 1)[0].strip()
    return {"L": "LW", "R": "RW"}.get(text, text if text in {"C", "LW", "RW", "D", "G", "F"} else None)


def _nationality(value: Any) -> str | None:
    match = re.search(r"[A-Z]{3}", str(value or "").upper())
    return match.group(0) if match else None


def _number(value: Any, integer: bool = False) -> int | float | None:
    if value in (None, "", "NA", "N/A"):
        return None
    try:
        number = Decimal(str(value))
        if not number.is_finite():
            return None
        return int(number) if integer else float(number)
    except (InvalidOperation, ValueError, TypeError):
        return None


def _money_cents(value: Any) -> int | None:
    if value in (None, ""):
        return None
    cleaned = re.sub(r"[^0-9.-]", "", str(value))
    if not cleaned:
        return None
    try:
        return int((Decimal(cleaned) * 100).quantize(Decimal("1")))
    except InvalidOperation:
        return None


def _capwages_birth_date(value: Any) -> str | None:
    match = re.fullmatch(r"(\d{2})-(\d{1,2})-(\d{1,2})", str(value or ""))
    if not match:
        return None
    year, month, day = (int(part) for part in match.groups())
    year += 1900 if year >= 30 else 2000
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _slug_from_name(name: str) -> str:
    first, last = _split_name(name)
    ascii_name = unicodedata.normalize("NFKD", f"{first} {last}").encode("ascii", "ignore").decode()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", ascii_name.lower())).strip("-")


def _row_hash(row: dict[str, Any]) -> str:
    encoded = json.dumps(row, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _source_ids(cursor) -> dict[str, int]:
    cursor.execute("SELECT code, id FROM data_sources")
    return {code: source_id for code, source_id in cursor.fetchall()}


def _team_ids(cursor) -> dict[str, int]:
    cursor.execute("SELECT abbreviation, id FROM teams")
    return {abbr: team_id for abbr, team_id in cursor.fetchall()}


def _ensure_seasons(cursor, years: Iterable[int]) -> None:
    rows = [(year, year + 1, f"{year}-{str(year + 1)[-2:]}") for year in sorted(set(years))]
    if rows:
        execute_values(
            cursor,
            """INSERT INTO seasons (start_year,end_year,label) VALUES %s
               ON CONFLICT (start_year) DO NOTHING""",
            rows,
        )


def _ensure_teams(cursor, abbreviations: Iterable[str], details: dict[str, dict] | None = None) -> dict[str, int]:
    details = details or {}
    rows = []
    for abbreviation in sorted({str(item).strip().upper() for item in abbreviations if item}):
        if not re.fullmatch(r"[A-Z]{2,4}", abbreviation) or abbreviation in {"ALL", "TOT"}:
            continue
        item = details.get(abbreviation, {})
        rows.append((
            abbreviation,
            item.get("name") or abbreviation,
            item.get("city"),
            item.get("nhl_team_id"),
            item.get("nhl_franchise_id"),
        ))
    if rows:
        execute_values(
            cursor,
            """INSERT INTO teams
                   (abbreviation, name, city, nhl_team_id, nhl_franchise_id)
               VALUES %s
               ON CONFLICT (abbreviation) DO UPDATE SET
                   name = CASE WHEN EXCLUDED.name = EXCLUDED.abbreviation THEN teams.name ELSE EXCLUDED.name END,
                   city = COALESCE(EXCLUDED.city, teams.city),
                   nhl_team_id = COALESCE(EXCLUDED.nhl_team_id, teams.nhl_team_id),
                   nhl_franchise_id = COALESCE(EXCLUDED.nhl_franchise_id, teams.nhl_franchise_id),
                   updated_at = CURRENT_TIMESTAMP""",
            rows,
        )
    return _team_ids(cursor)


def _upsert_player(cursor, source_id: int, external_id: Any, full_name: str, **fields: Any) -> int:
    external_text = str(external_id)
    cursor.execute(
        "SELECT player_id FROM player_external_ids WHERE source_id = %s AND external_id = %s",
        (source_id, external_text),
    )
    found = cursor.fetchone()
    first_name, last_name = _split_name(full_name)
    if found:
        player_id = found[0]
        cursor.execute(
            """UPDATE players SET
                   first_name = COALESCE(%s, first_name), last_name = COALESCE(%s, last_name),
                   birth_date = COALESCE(%s, birth_date),
                   primary_position = COALESCE(%s, primary_position),
                   shoots_catches = COALESCE(%s, shoots_catches),
                   nationality = COALESCE(%s, nationality), updated_at = CURRENT_TIMESTAMP
               WHERE id = %s""",
            (first_name or None, last_name or None, fields.get("birth_date"), fields.get("position"),
             fields.get("shoots_catches"), fields.get("nationality"), player_id),
        )
    else:
        cursor.execute(
            """INSERT INTO players
                   (first_name, last_name, birth_date, primary_position, shoots_catches, nationality)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
            (first_name or "Unknown", last_name or "Unknown", fields.get("birth_date"), fields.get("position"),
             fields.get("shoots_catches"), fields.get("nationality")),
        )
        player_id = cursor.fetchone()[0]
        cursor.execute(
            """INSERT INTO player_external_ids
                   (player_id, source_id, external_id, source_slug, source_name)
               VALUES (%s, %s, %s, %s, %s)""",
            (player_id, source_id, external_text, fields.get("source_slug"), full_name),
        )
    return player_id


def _link_external_id(cursor, player_id: int, source_id: int, external_id: str, name: str, slug: str | None = None) -> None:
    cursor.execute(
        """INSERT INTO player_external_ids
               (player_id, source_id, external_id, source_slug, source_name)
           VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT (source_id, external_id) DO UPDATE SET
               source_slug = COALESCE(EXCLUDED.source_slug, player_external_ids.source_slug),
               source_name = EXCLUDED.source_name, updated_at = CURRENT_TIMESTAMP""",
        (player_id, source_id, external_id, slug, name),
    )


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _download_csv(session: requests.Session, url: str) -> list[dict[str, str]]:
    response = session.get(url, timeout=60)
    response.raise_for_status()
    return list(csv.DictReader(io.StringIO(response.text)))


def ingest_moneypuck(session: requests.Session) -> dict[str, int]:
    frames = {}
    for kind in ("skater", "goalie"):
        frames[kind] = _read_csv(MONEYPUCK_FILES[kind]) + _download_csv(session, MONEYPUCK_URLS[kind])

    with database_transaction() as connection:
        cursor = connection.cursor()
        source_id = _source_ids(cursor)["moneypuck"]
        team_ids = _ensure_teams(cursor, (row.get("team") for rows in frames.values() for row in rows))
        player_ids: dict[str, int] = {}
        latest: dict[str, tuple[int, str, str, bool]] = {}
        for kind, rows in frames.items():
            for row in rows:
                external_id = str(row.get("playerId") or "").strip()
                if not external_id:
                    continue
                season = int(row.get("season") or 0)
                candidate = (season, row.get("name") or "Unknown", row.get("position") or "", kind == "goalie")
                if external_id not in latest or season >= latest[external_id][0]:
                    latest[external_id] = candidate
        for external_id, (_, name, position, goalie) in latest.items():
            player_ids[external_id] = _upsert_player(
                cursor, source_id, external_id, name, position=_position(position, goalie)
            )

        counts = {}
        for kind, rows in frames.items():
            values = []
            for row in rows:
                external_id = str(row.get("playerId") or "").strip()
                player_id = player_ids.get(external_id)
                season = _number(row.get("season"), integer=True)
                if player_id is None or season is None:
                    continue
                team_abbr = str(row.get("team") or "").upper()
                team_id = team_ids.get(team_abbr)
                stat_scope = "TEAM" if team_id else "TOTAL"
                situation = str(row.get("situation") or "all")[:24]
                extra = {key: _number(value) if value not in (None, "") else None for key, value in row.items()}
                if kind == "skater":
                    values.append((
                        player_id, season, team_id, stat_scope, situation, source_id,
                        _number(row.get("games_played"), True), _number(row.get("icetime")),
                        _number(row.get("shifts"), True), _number(row.get("gameScore")),
                        _number(row.get("I_F_points"), True), _number(row.get("I_F_goals"), True),
                        _number(row.get("I_F_primaryAssists"), True), _number(row.get("I_F_secondaryAssists"), True),
                        _number(row.get("I_F_xGoals")), _number(row.get("I_F_shotsOnGoal"), True),
                        _number(row.get("I_F_unblockedShotAttempts"), True), _number(row.get("onIce_xGoalsPercentage")),
                        _number(row.get("shotsBlockedByPlayer"), True), _number(row.get("I_F_takeaways"), True),
                        _number(row.get("I_F_giveaways"), True), _number(row.get("penalties"), True),
                        _number(row.get("penaltiesDrawn"), True), _number(row.get("I_F_oZoneShiftStarts"), True),
                        _number(row.get("I_F_dZoneShiftStarts"), True), _number(row.get("I_F_neutralZoneShiftStarts"), True),
                        Json(extra), _row_hash(row),
                    ))
                else:
                    values.append((
                        player_id, season, team_id, stat_scope, situation, source_id,
                        _number(row.get("games_played"), True), _number(row.get("icetime")), _number(row.get("xGoals")),
                        _number(row.get("goals")), _number(row.get("unblocked_shot_attempts"), True),
                        _number(row.get("blocked_shot_attempts"), True), _number(row.get("xRebounds")),
                        _number(row.get("rebounds"), True), _number(row.get("xFreeze")), _number(row.get("freeze"), True),
                        _number(row.get("xOnGoal")), _number(row.get("ongoal"), True),
                        _number(row.get("flurryAdjustedxGoals")), _number(row.get("lowDangerShots"), True),
                        _number(row.get("mediumDangerShots"), True), _number(row.get("highDangerShots"), True),
                        _number(row.get("lowDangerxGoals")), _number(row.get("mediumDangerxGoals")),
                        _number(row.get("highDangerxGoals")), _number(row.get("lowDangerGoals"), True),
                        _number(row.get("mediumDangerGoals"), True), _number(row.get("highDangerGoals"), True),
                        Json(extra), _row_hash(row),
                    ))
            if kind == "skater":
                columns = """player_id,season_start_year,team_id,stat_scope,situation,source_id,games_played,
                    ice_time_seconds,shifts,game_score,individual_points,individual_goals,individual_primary_assists,
                    individual_secondary_assists,individual_expected_goals,individual_shots_on_goal,
                    individual_unblocked_attempts,on_ice_expected_goals_pct,shots_blocked,takeaways,giveaways,
                    penalties,penalties_drawn,offensive_zone_shift_starts,defensive_zone_shift_starts,
                    neutral_zone_shift_starts,extra_metrics,source_row_hash"""
                table = "skater_advanced_season_stats"
            else:
                columns = """player_id,season_start_year,team_id,stat_scope,situation,source_id,games_played,
                    ice_time_seconds,expected_goals_against,goals_against,unblocked_shot_attempts,
                    blocked_shot_attempts,expected_rebounds,rebounds,expected_freezes,freezes,
                    expected_shots_on_goal,shots_on_goal,flurry_adjusted_expected_goals,low_danger_shots,
                    medium_danger_shots,high_danger_shots,low_danger_expected_goals,medium_danger_expected_goals,
                    high_danger_expected_goals,low_danger_goals,medium_danger_goals,high_danger_goals,
                    extra_metrics,source_row_hash"""
                table = "goalie_advanced_season_stats"
            execute_values(
                cursor,
                f"""INSERT INTO {table} ({columns}) VALUES %s
                    ON CONFLICT (player_id,season_start_year,(COALESCE(team_id,0)),stat_scope,game_type,situation,source_id)
                    DO UPDATE SET extra_metrics=EXCLUDED.extra_metrics, source_row_hash=EXCLUDED.source_row_hash,
                        updated_at=CURRENT_TIMESTAMP""",
                values,
                page_size=1000,
            )
            counts[kind] = len(values)
        cursor.close()
    LOGGER.info("MoneyPuck loaded: players=%s skater_rows=%s goalie_rows=%s", len(player_ids), counts["skater"], counts["goalie"])
    return {"players": len(player_ids), **counts}


def ingest_nhl_rosters(session: requests.Session) -> dict[str, int]:
    standings = session.get("https://api-web.nhle.com/v1/standings/now", timeout=30).json().get("standings", [])
    teams = {}
    for row in standings:
        abbreviation = _default(row.get("teamAbbrev"))
        if abbreviation:
            teams[abbreviation] = {
                "name": _default(row.get("teamName")),
                "city": _default(row.get("placeName")),
            }
    rosters = {}
    for abbreviation in teams:
        response = session.get(f"https://api-web.nhle.com/v1/roster/{abbreviation}/current", timeout=30)
        response.raise_for_status()
        rosters[abbreviation] = response.json()

    with database_transaction() as connection:
        cursor = connection.cursor()
        source_ids = _source_ids(cursor)
        moneypuck_id, nhl_id = source_ids["moneypuck"], source_ids["nhl"]
        team_ids = _ensure_teams(cursor, teams, teams)
        active = 0
        for abbreviation, roster in rosters.items():
            for group in ("forwards", "defensemen", "goalies"):
                for row in roster.get(group, []):
                    external_id = str(row["id"])
                    full_name = f"{_default(row.get('firstName')) or ''} {_default(row.get('lastName')) or ''}".strip()
                    cursor.execute(
                        "SELECT player_id FROM player_external_ids WHERE source_id=%s AND external_id=%s",
                        (moneypuck_id, external_id),
                    )
                    found = cursor.fetchone()
                    if found:
                        player_id = found[0]
                        _link_external_id(cursor, player_id, nhl_id, external_id, full_name)
                        cursor.execute(
                            """UPDATE players SET first_name=%s,last_name=%s,birth_date=%s,primary_position=%s,
                                   shoots_catches=%s,nationality=%s,active=TRUE,updated_at=CURRENT_TIMESTAMP WHERE id=%s""",
                            (*_split_name(full_name), row.get("birthDate"), _position(row.get("positionCode"), group == "goalies"),
                             row.get("shootsCatches"), row.get("birthCountry"), player_id),
                        )
                    else:
                        player_id = _upsert_player(
                            cursor, nhl_id, external_id, full_name, birth_date=row.get("birthDate"),
                            position=_position(row.get("positionCode"), group == "goalies"),
                            shoots_catches=row.get("shootsCatches"), nationality=_nationality(row.get("birthCountry")),
                        )
                    cursor.execute(
                        """INSERT INTO player_team_stints (player_id,season_start_year,team_id,roster_status)
                           VALUES (%s,2026,%s,'ACTIVE') ON CONFLICT DO NOTHING""",
                        (player_id, team_ids[abbreviation]),
                    )
                    active += 1
        cursor.close()
    LOGGER.info("NHL rosters loaded: teams=%s active_players=%s", len(teams), active)
    return {"teams": len(teams), "active_players": active}


def _nhl_stats_pages(session: requests.Session, endpoint: str, season: int, game_type: int) -> list[dict]:
    rows = []
    start = 0
    while True:
        response = session.get(
            f"https://api.nhle.com/stats/rest/en/{endpoint}/summary",
            params={
                "isAggregate": "false", "isGame": "false", "start": start, "limit": 100,
                "cayenneExp": f"seasonId={season}{season + 1} and gameTypeId={game_type}",
            },
            timeout=30,
        )
        response.raise_for_status()
        page = response.json().get("data", [])
        rows.extend(page)
        if len(page) < 100:
            break
        start += len(page)
    return rows


def ingest_nhl_stats(session: requests.Session, first_season: int = 2008, last_season: int = 2025) -> dict[str, int]:
    fetched = defaultdict(list)
    jobs = [(kind, season, game_type) for kind in ("skater", "goalie")
            for season in range(first_season, last_season + 1) for game_type in (2, 3)]
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(_nhl_stats_pages, session, *job): job for job in jobs}
        for future in as_completed(futures):
            kind, season, game_type = futures[future]
            fetched[kind].extend((season, game_type, row) for row in future.result())

    with database_transaction() as connection:
        cursor = connection.cursor()
        source_ids = _source_ids(cursor)
        nhl_id, moneypuck_id = source_ids["nhl"], source_ids["moneypuck"]
        abbreviations = []
        for rows in fetched.values():
            for _, _, row in rows:
                team = str(row.get("teamAbbrevs") or "")
                if "," not in team:
                    abbreviations.append(team)
        team_ids = _ensure_teams(cursor, abbreviations)
        player_cache = {}
        counts = {}
        for kind, records in fetched.items():
            values_by_grain = {}
            for season, game_type, row in records:
                external_id = str(row.get("playerId") or "")
                if not external_id:
                    continue
                if external_id not in player_cache:
                    cursor.execute(
                        "SELECT player_id FROM player_external_ids WHERE source_id IN (%s,%s) AND external_id=%s ORDER BY source_id=%s DESC LIMIT 1",
                        (nhl_id, moneypuck_id, external_id, nhl_id),
                    )
                    found = cursor.fetchone()
                    name = row.get("skaterFullName") or row.get("goalieFullName") or row.get("lastName") or "Unknown"
                    player_id = found[0] if found else _upsert_player(
                        cursor, nhl_id, external_id, name,
                        position=_position(row.get("positionCode"), kind == "goalie"),
                        shoots_catches=row.get("shootsCatches"),
                    )
                    _link_external_id(cursor, player_id, nhl_id, external_id, name)
                    player_cache[external_id] = player_id
                player_id = player_cache[external_id]
                team_text = str(row.get("teamAbbrevs") or "")
                team_id = team_ids.get(team_text) if "," not in team_text else None
                scope = "TEAM" if team_id else "TOTAL"
                if kind == "skater":
                    value = (player_id, season, team_id, scope, game_type, nhl_id,
                        _number(row.get("gamesPlayed"), True), _number(row.get("goals"), True),
                        _number(row.get("assists"), True), _number(row.get("points"), True),
                        _number(row.get("plusMinus"), True), _number(row.get("penaltyMinutes"), True),
                        _number(row.get("ppGoals"), True), _number(row.get("ppPoints"), True),
                        _number(row.get("shGoals"), True), _number(row.get("shots"), True),
                        _number(row.get("shootingPct")), _row_hash(row))
                else:
                    value = (player_id, season, team_id, scope, game_type, nhl_id,
                        _number(row.get("gamesPlayed"), True), _number(row.get("wins"), True),
                        _number(row.get("losses"), True), _number(row.get("otLosses"), True),
                        _number(row.get("shotsAgainst"), True), _number(row.get("saves"), True),
                        _number(row.get("savePct")), _number(row.get("goalsAgainst"), True),
                        _number(row.get("goalsAgainstAverage")), _number(row.get("shutouts"), True),
                        _number(row.get("timeOnIce"), True), _row_hash(row))
                values_by_grain[(player_id, season, team_id or 0, scope, game_type, nhl_id)] = value
            values = list(values_by_grain.values())
            if kind == "skater":
                columns = "player_id,season_start_year,team_id,stat_scope,game_type,source_id,games_played,goals,assists,points,plus_minus,penalty_minutes,power_play_goals,power_play_points,short_handed_goals,shots,shooting_percentage,source_row_hash"
                table = "skater_season_stats"
                update_columns = """games_played=EXCLUDED.games_played,goals=EXCLUDED.goals,
                    assists=EXCLUDED.assists,points=EXCLUDED.points,plus_minus=EXCLUDED.plus_minus,
                    penalty_minutes=EXCLUDED.penalty_minutes,power_play_goals=EXCLUDED.power_play_goals,
                    power_play_points=EXCLUDED.power_play_points,short_handed_goals=EXCLUDED.short_handed_goals,
                    shots=EXCLUDED.shots,shooting_percentage=EXCLUDED.shooting_percentage"""
            else:
                columns = "player_id,season_start_year,team_id,stat_scope,game_type,source_id,games_played,wins,losses,overtime_losses,shots_against,saves,save_percentage,goals_against,goals_against_average,shutouts,time_on_ice_seconds,source_row_hash"
                table = "goalie_season_stats"
                update_columns = """games_played=EXCLUDED.games_played,wins=EXCLUDED.wins,losses=EXCLUDED.losses,
                    overtime_losses=EXCLUDED.overtime_losses,shots_against=EXCLUDED.shots_against,
                    saves=EXCLUDED.saves,save_percentage=EXCLUDED.save_percentage,
                    goals_against=EXCLUDED.goals_against,goals_against_average=EXCLUDED.goals_against_average,
                    shutouts=EXCLUDED.shutouts,time_on_ice_seconds=EXCLUDED.time_on_ice_seconds"""
            execute_values(cursor, f"""INSERT INTO {table} ({columns}) VALUES %s
                ON CONFLICT (player_id,season_start_year,(COALESCE(team_id,0)),stat_scope,game_type,source_id)
                DO UPDATE SET {update_columns},source_row_hash=EXCLUDED.source_row_hash,
                    updated_at=CURRENT_TIMESTAMP""", values, page_size=1000)
            counts[kind] = len(values)
        cursor.close()
    LOGGER.info("NHL stats loaded: skater_rows=%s goalie_rows=%s", counts["skater"], counts["goalie"])
    return counts


def _capwages_active(session: requests.Session) -> list[list[Any]]:
    response = session.get("https://capwages.com/players/active", timeout=60)
    response.raise_for_status()
    match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', response.text, re.DOTALL)
    if not match:
        raise RuntimeError("CapWages active-player page no longer contains __NEXT_DATA__")
    players = json.loads(match.group(1)).get("props", {}).get("pageProps", {}).get("playersArray", [])
    if len(players) < 500:
        raise RuntimeError(f"CapWages returned an unexpectedly partial active-player list ({len(players)} rows)")
    return players


def _capwages_contracts(session: requests.Session, slug: str) -> list[dict]:
    response = session.get(f"https://capwages.com/players/{slug}", timeout=30)
    response.raise_for_status()
    match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', response.text, re.DOTALL)
    if not match:
        return []
    return json.loads(match.group(1)).get("props", {}).get("pageProps", {}).get("player", {}).get("contracts", [])


def ingest_capwages(session: requests.Session) -> dict[str, int]:
    active = _capwages_active(session)
    players = []
    for row in active:
        if not isinstance(row, list) or len(row) < 4:
            continue
        slug = row[1] or _slug_from_name(row[0])
        if not slug:
            continue
        players.append({"name": row[0], "slug": slug, "team": row[2], "position": row[3],
                        "nationality": row[7] if len(row) > 7 else None,
                        "birth_date": _capwages_birth_date(row[30] if len(row) > 30 else None)})
    if len(players) < 500:
        raise RuntimeError(f"Only {len(players)} CapWages player rows could be assigned profile slugs")
    contracts_by_slug = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(_capwages_contracts, session, item["slug"]): item["slug"] for item in players}
        for future in as_completed(futures):
            slug = futures[future]
            try:
                contracts_by_slug[slug] = future.result()
            except requests.RequestException as exc:
                LOGGER.warning("CapWages profile unavailable for %s: %s", slug, exc)
                contracts_by_slug[slug] = []

    with database_transaction() as connection:
        cursor = connection.cursor()
        sources = _source_ids(cursor)
        capwages_id = sources["capwages"]
        contract_teams = [
            contract.get("signingTeam")
            for contracts in contracts_by_slug.values()
            for contract in contracts
        ]
        team_ids = _ensure_teams(cursor, [item["team"] for item in players] + contract_teams)
        contract_years = []
        for contracts in contracts_by_slug.values():
            for contract in contracts:
                for detail in contract.get("details") or []:
                    match = re.match(r"(\d{4})", str(detail.get("season") or ""))
                    if match:
                        contract_years.append(int(match.group(1)))
        _ensure_seasons(cursor, contract_years)
        cursor.execute("""SELECT p.id, lower(p.first_name), lower(p.last_name) FROM players p""")
        by_name = defaultdict(list)
        for player_id, first, last in cursor.fetchall():
            by_name[(first, last)].append(player_id)
        contract_count = season_count = 0
        for item in players:
            first, last = _split_name(item["name"])
            matches = by_name.get((first.lower(), last.lower()), [])
            if len(matches) == 1:
                player_id = matches[0]
                _link_external_id(cursor, player_id, capwages_id, item["slug"], item["name"], item["slug"])
            else:
                player_id = _upsert_player(cursor, capwages_id, item["slug"], item["name"],
                    source_slug=item["slug"], birth_date=item["birth_date"],
                    position=_position(item["position"]), nationality=_nationality(item["nationality"]))
                by_name[(first.lower(), last.lower())].append(player_id)
            for index, contract in enumerate(contracts_by_slug.get(item["slug"], [])):
                details = contract.get("details") or []
                if not details:
                    continue
                years = []
                for detail in details:
                    match = re.match(r"(\d{4})", str(detail.get("season") or ""))
                    if match:
                        years.append(int(match.group(1)))
                if not years:
                    continue
                start, end = min(years), max(years)
                external_id = f"{item['slug']}:{start}:{end}:{index}"
                total_cents = _money_cents(contract.get("value"))
                average_cents = _money_cents(details[0].get("capHit"))
                expiry = str(contract.get("expiryStatus") or "").upper()
                expiry = "RFA" if "RFA" in expiry else "UFA" if "UFA" in expiry else None
                contract_type = str(contract.get("type") or "")[:32] or None
                cursor.execute(
                    """INSERT INTO contracts (player_id,signing_team_id,source_id,external_id,start_season,end_season,
                           term_years,contract_type,expiry_status,total_value_cents,average_value_cents,is_entry_level,source_payload)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (source_id,external_id) WHERE source_id IS NOT NULL AND external_id IS NOT NULL
                       DO UPDATE SET total_value_cents=EXCLUDED.total_value_cents,average_value_cents=EXCLUDED.average_value_cents,
                           source_payload=EXCLUDED.source_payload,updated_at=CURRENT_TIMESTAMP RETURNING id""",
                    (player_id, team_ids.get(str(contract.get("signingTeam") or item["team"]).upper()), capwages_id,
                     external_id, start, end, len(years), contract_type, expiry, total_cents, average_cents,
                     "ENTRY" in (contract_type or "").upper() or "ELC" in (contract_type or "").upper(), Json(contract)),
                )
                contract_id = cursor.fetchone()[0]
                contract_count += 1
                for detail in details:
                    match = re.match(r"(\d{4})", str(detail.get("season") or ""))
                    if not match:
                        continue
                    year = int(match.group(1))
                    cap_hit = _money_cents(detail.get("capHit")) or 0
                    cursor.execute("SELECT salary_cap_cents FROM seasons WHERE start_year=%s", (year,))
                    cap_row = cursor.fetchone()
                    cap_pct = Decimal(cap_hit) / cap_row[0] if cap_row and cap_row[0] else None
                    cursor.execute(
                        """INSERT INTO contract_seasons (contract_id,season_start_year,owning_team_id,cap_hit_cents,cap_percentage,is_slide)
                           VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (contract_id,season_start_year) DO UPDATE SET
                           cap_hit_cents=EXCLUDED.cap_hit_cents,cap_percentage=EXCLUDED.cap_percentage,
                           is_slide=EXCLUDED.is_slide,updated_at=CURRENT_TIMESTAMP""",
                        (contract_id, year, team_ids.get(item["team"]), cap_hit, cap_pct,
                         "slide" in str(detail.get("type") or "").lower()),
                    )
                    season_count += 1
        cursor.close()
    LOGGER.info("CapWages loaded: active_players=%s contracts=%s contract_seasons=%s", len(players), contract_count, season_count)
    return {"players": len(players), "contracts": contract_count, "contract_seasons": season_count}


def existing_capwages_summary() -> dict[str, int]:
    """Return the durable last-good CapWages snapshot already in PostgreSQL."""
    with database_transaction() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """SELECT
                   (SELECT count(DISTINCT external.player_id)
                      FROM player_external_ids external WHERE external.source_id = source.id),
                   (SELECT count(*) FROM contracts WHERE contracts.source_id = source.id),
                   (SELECT count(*) FROM contract_seasons
                      JOIN contracts ON contracts.id = contract_seasons.contract_id
                     WHERE contracts.source_id = source.id)
               FROM data_sources source WHERE source.code = 'capwages'"""
        )
        players, contracts, contract_seasons = cursor.fetchone()
        cursor.close()
    if not contracts:
        raise RuntimeError("CapWages is unavailable and no last-good database snapshot exists")
    return {
        "players": players,
        "contracts": contracts,
        "contract_seasons": contract_seasons,
        "cached": 1,
    }


def ingest_schedule(session: requests.Session, season: int = 2026) -> dict[str, int]:
    cursor_date = f"{season}-10-01"
    games = {}
    while cursor_date:
        response = session.get(f"https://api-web.nhle.com/v1/schedule/{cursor_date}", timeout=30)
        response.raise_for_status()
        payload = response.json()
        for day in payload.get("gameWeek", []):
            for game in day.get("games", []):
                if game.get("gameType") == 2:
                    game["_game_date"] = day["date"]
                    games[game["id"]] = game
        next_date = payload.get("nextStartDate")
        if not next_date or next_date <= cursor_date or next_date[:4] > str(season + 1):
            break
        cursor_date = next_date
    with database_transaction() as connection:
        cursor = connection.cursor()
        abbreviations = [game[side]["abbrev"] for game in games.values() for side in ("awayTeam", "homeTeam")]
        team_ids = _ensure_teams(cursor, abbreviations)
        for game in games.values():
            cursor.execute(
                """INSERT INTO games (nhl_game_id,season_start_year,game_type,game_date,start_time_utc,
                       away_team_id,home_team_id,venue,game_state,away_score,home_score,last_synced_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
                   ON CONFLICT (nhl_game_id) DO UPDATE SET game_state=EXCLUDED.game_state,
                       away_score=EXCLUDED.away_score,home_score=EXCLUDED.home_score,last_synced_at=CURRENT_TIMESTAMP,
                       updated_at=CURRENT_TIMESTAMP""",
                (game["id"], season, game["gameType"], game["_game_date"], game.get("startTimeUTC"),
                 team_ids[game["awayTeam"]["abbrev"]], team_ids[game["homeTeam"]["abbrev"]],
                 _default(game.get("venue")), game.get("gameState"), game["awayTeam"].get("score"),
                 game["homeTeam"].get("score")),
            )
        cursor.close()
    LOGGER.info("NHL schedule loaded: games=%s", len(games))
    return {"games": len(games)}


def run_all() -> dict[str, dict[str, int]]:
    init_db()
    session = http_session()
    results = {}
    results["moneypuck"] = ingest_moneypuck(session)
    results["nhl_rosters"] = ingest_nhl_rosters(session)
    results["nhl_stats"] = ingest_nhl_stats(session)
    try:
        results["capwages"] = ingest_capwages(session)
    except (requests.RequestException, RuntimeError) as exc:
        results["capwages"] = existing_capwages_summary()
        LOGGER.warning("CapWages refresh unavailable; retained last-good database snapshot: %s", exc)
    results["schedule"] = ingest_schedule(session)
    return results
