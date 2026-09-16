import sys
import os
import traceback

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import requests
import time
from sqlalchemy.orm import Session
from decimal import Decimal
from app.database import SessionLocal, init_db
from app.models import Player, Contract, BasicPlayerStats, BasicGoalieStats

# cd backend && DB_HOST=localhost python3 -m app.ScriptingFiles.save_basic_player_stats

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
}

def make_request_with_rate_limit(url, delay=0.5, max_retries=3):
    """Makes an API request with some delays to avoid getting rate limited, and retries if things go wrong"""
    for attempt in range(max_retries):
        try:
            time.sleep(delay)
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 60))
                time.sleep(retry_after)
                continue
            
            if response.status_code != 200:
                if response.status_code >= 500:
                    time.sleep(5)
                    continue
                else:
                    return None
            
            try:
                return response.json()
            except ValueError as e:
                return None
                
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                return None
    
    return None


def get_skater_stats():
    """Grabs all the player stats from the NHL API and saves them to the database"""
    
    active_ids = set()
    
    try:
        teams_resp = make_request_with_rate_limit("https://api-web.nhle.com/v1/standings/now", delay=1)
        if not teams_resp:
            return False
        
        team_abbrs = [t['teamAbbrev']['default'] for t in teams_resp.get('standings', [])]
    except Exception as e:
        traceback.print_exc()
        return False

    skipped_teams = []
    for i, abbr in enumerate(team_abbrs):
        roster_url = f"https://api-web.nhle.com/v1/roster/{abbr}/current"
        roster = make_request_with_rate_limit(roster_url, delay=0.5)
        if not roster:
            skipped_teams.append(abbr)
            continue
        
        player_count = 0
        for group in ['forwards', 'defensemen', 'goalies']:
            for player in roster.get(group, []):
                if 'id' in player:
                    active_ids.add(player['id'])
                    player_count += 1
            
    all_rows = []
    
    stats_base_url = "https://api.nhle.com/stats/rest/en/skater/summary"
    
    for i, pid in enumerate(active_ids):
        for game_type in [2, 3]:
            params = {
                "isAggregate": "false",
                "isGame": "false",
                "start": 0,
                "limit": 100,
                "cayenneExp": f"playerId={pid} and gameTypeId={game_type}"
            }
            
            try:
                time.sleep(0.1)
                resp = requests.get(stats_base_url, params=params, headers=headers, timeout=10)
                
                if resp.status_code == 429:
                    retry_after = int(resp.headers.get('Retry-After', 60))
                    time.sleep(retry_after)
                    resp = requests.get(stats_base_url, params=params, headers=headers, timeout=10)
                
                if resp.status_code != 200:
                    continue
                
                data = resp.json().get('data', [])
                
                for season_entry in data:
                    s_id = str(season_entry.get('seasonId'))
                    season_int = int(s_id[:4])
                    
                    stats_record = {
                        'player_id_nhl': pid,
                        'player_name': season_entry.get('skaterFullName'),
                        'season': season_int,
                        'season_type': 'Regular' if game_type == 2 else 'Playoffs',
                        'team': season_entry.get('teamAbbrevs'),
                        'games_played': season_entry.get('gamesPlayed'),
                        'goals': season_entry.get('goals'),
                        'assists': season_entry.get('assists'),
                        'points': season_entry.get('points'),
                        'plus_minus': season_entry.get('plusMinus'),
                        'penalty_minutes': season_entry.get('penaltyMinutes'),
                        'pp_goals': season_entry.get('ppGoals'),
                        'pp_points': season_entry.get('ppPoints'),
                        'sh_goals': season_entry.get('shGoals'),
                        'shots': season_entry.get('shots'),
                        'shooting_pct': Decimal(str(season_entry.get('shootingPct'))) if season_entry.get('shootingPct') is not None else None
                    }
                    all_rows.append(stats_record)
                    
            except Exception as e:
                pass

    save_stats_to_db(all_rows)

def get_goalie_stats():
    """Grabs all the goalie stats from the NHL API and saves them to the database"""
    active_ids = set()
    
    try:
        teams_resp = make_request_with_rate_limit("https://api-web.nhle.com/v1/standings/now", delay=1)
        if not teams_resp:
            return False
        
        team_abbrs = [t['teamAbbrev']['default'] for t in teams_resp.get('standings', [])]
    except Exception as e:
        traceback.print_exc()
        return False

    for i, abbr in enumerate(team_abbrs):
        roster_url = f"https://api-web.nhle.com/v1/roster/{abbr}/current"
        roster = make_request_with_rate_limit(roster_url, delay=0.5)
        
        if not roster:
            continue

        player_count = 0
        for group in ['goalies']:
            for player in roster.get(group, []):
                if 'id' in player:
                    active_ids.add(player['id'])
                    player_count += 1

    all_rows = []

    stats_base_url = "https://api.nhle.com/stats/rest/en/goalie/summary"

    for i, pid in enumerate(active_ids):
        for game_type in [2, 3]:
            params = {
                "isAggregate": "false",
                "isGame": "false",
                "start": 0,
                "limit": 100,
                "cayenneExp": f"playerId={pid} and gameTypeId={game_type}"
            }
            
            try:
                time.sleep(0.1)
                resp = requests.get(stats_base_url, params=params, headers=headers, timeout=10)
                
                if resp.status_code == 429:
                    retry_after = int(resp.headers.get('Retry-After', 60))
                    time.sleep(retry_after)
                    resp = requests.get(stats_base_url, params=params, headers=headers, timeout=10)
                
                if resp.status_code != 200:
                    continue
                
                data = resp.json().get('data', [])
                for season_entry in data:
                    s_id = str(season_entry.get('seasonId'))
                    season_int = int(s_id[:4])
                    
                    stats_record = {
                        'player_name': season_entry.get('goalieFullName'),
                        'season': season_int,
                        'season_type': 'Regular' if game_type == 2 else 'Playoffs',
                        'team': season_entry.get('teamAbbrevs'),
                        'games_played': season_entry.get('gamesPlayed'),
                        'wins': season_entry.get('wins'),
                        'losses': season_entry.get('losses'),
                        'ot_losses': season_entry.get('otLosses'),
                        'shots_against': season_entry.get('shotsAgainst'),
                        'saves': season_entry.get('saves'),
                        'save_percentage': Decimal(str(season_entry.get('savePct'))) if season_entry.get('savePct') is not None else None,
                        'goals_against': season_entry.get('goalsAgainst'),
                        'goals_against_average': season_entry.get('goalsAgainstAverage'),
                        'shutouts': season_entry.get('shutouts'),
                        'time_on_ice': season_entry.get('timeOnIce'),
                    }
                    all_rows.append(stats_record)
                    
            except Exception as e:
                pass

    save_goalie_stats_to_db(all_rows)

def save_goalie_stats_to_db(stats_records):
    """Takes all the goalie stats and saves them to the database, matching players and contracts along the way"""
    init_db()
    
    db: Session = SessionLocal()
    try:
        created_count = 0
        updated_count = 0
        skipped_count = 0
        
        for record in stats_records:
            player_name = record.get('player_name', '')
            firstname, lastname = parse_player_name(player_name)
            
            if not firstname or not lastname:
                skipped_count += 1
                continue

            player = db.query(Player).filter(
                Player.firstname.ilike(firstname),
                Player.lastname.ilike(lastname)
            ).first()
            
            if not player:
                skipped_count += 1
                continue
            
            season_int = record.get('season')
            playoff = record.get('season_type', '').lower() == 'playoffs'
            
            contract = db.query(Contract).filter(
                Contract.player_id == player.id,
                Contract.start_year <= season_int,
                Contract.end_year >= season_int
            ).first()
            
            if not contract:
                skipped_count += 1
                continue
            
            gp = record.get('games_played') or 0
            wins = record.get('wins') or 0
            losses = record.get('losses') or 0
            ot_losses = record.get('ot_losses') or 0
            shots_against = record.get('shots_against') or 0
            saves = record.get('saves') or 0
            save_percentage = record.get('save_percentage') or Decimal('0.00')
            goals_against = record.get('goals_against') or 0
            goals_against_average = record.get('goals_against_average') or 0
            shutouts = record.get('shutouts') or 0
            time_on_ice = record.get('time_on_ice') or 0
            
            if isinstance(save_percentage, Decimal):
                save_percentage = save_percentage * 100
            
            team = record.get('team', '')
            if not team:
                skipped_count += 1
                continue
            
            existing = db.query(BasicGoalieStats).filter(
                BasicGoalieStats.player_id == player.id,
                BasicGoalieStats.contract_id == contract.id,
                BasicGoalieStats.season == season_int,
                BasicGoalieStats.playoff == playoff
            ).first()
            
            if existing:
                existing.team = team
                existing.gp = gp
                existing.wins = wins
                existing.losses = losses
                existing.ot_losses = ot_losses
                existing.shots_against = shots_against
                existing.saves = saves
                existing.save_percentage = save_percentage
                existing.goals_against = goals_against
                existing.goals_against_average = goals_against_average
                existing.shutouts = shutouts
                existing.time_on_ice = time_on_ice
                updated_count += 1
            else:
                new_stats = BasicGoalieStats(
                    player_id=player.id,
                    contract_id=contract.id,
                    season=season_int,
                    playoff=playoff,
                    team=team,
                    gp=gp,
                    wins=wins,
                    losses=losses,
                    ot_losses=ot_losses,
                    shots_against=shots_against,
                    saves=saves,
                    save_percentage=save_percentage,
                    goals_against=goals_against,
                    goals_against_average=goals_against_average,
                    shutouts=shutouts,
                    time_on_ice=time_on_ice
                )
                db.add(new_stats)
                created_count += 1
            
            if (created_count + updated_count) % 100 == 0:
                db.commit()

    except Exception as e:
        db.rollback()
        traceback.print_exc()
    finally:
        db.close()

def parse_player_name(full_name: str):
    """Takes a full name and splits it into first and last name"""
    if not full_name:
        return None, None
    
    parts = full_name.strip().split(' ', 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    elif len(parts) == 1:
        return parts[0], ""
    return None, None


def save_stats_to_db(stats_records):
    """Takes all the scraped stats and saves them to the database, matching players and contracts along the way"""
    init_db()
    
    db: Session = SessionLocal()
    try:
        created_count = 0
        updated_count = 0
        skipped_count = 0
        
        for record in stats_records:    
            player_name = record.get('player_name', '')
            firstname, lastname = parse_player_name(player_name)
            
            if not firstname or not lastname:
                skipped_count += 1
                continue
            
            player = db.query(Player).filter(
                Player.firstname.ilike(firstname),
                Player.lastname.ilike(lastname)
            ).first()
            
            if not player:
                skipped_count += 1
                continue
            
            season_int = record.get('season')
            playoff = record.get('season_type', '').lower() == 'playoffs'
            
            contract = db.query(Contract).filter(
                Contract.player_id == player.id,
                Contract.start_year <= season_int,
                Contract.end_year >= season_int
            ).first()
            
            if not contract:
                skipped_count += 1
                continue
            
            gp = record.get('games_played') or 0
            goals = record.get('goals') or 0
            assists = record.get('assists') or 0
            points = record.get('points') or 0
            plus_minus = record.get('plus_minus') or 0
            pim = record.get('penalty_minutes') or 0
            shots = record.get('shots') or 0
            shooting_pct = record.get('shooting_pct') or Decimal('0.00')
            
            if isinstance(shooting_pct, Decimal):
                shooting_pct = shooting_pct * 100
            
            team = record.get('team', '')
            if not team:
                skipped_count += 1
                continue
            
            existing = db.query(BasicPlayerStats).filter(
                BasicPlayerStats.player_id == player.id,
                BasicPlayerStats.contract_id == contract.id,
                BasicPlayerStats.season == season_int,
                BasicPlayerStats.playoff == playoff
            ).first()
            
            if existing:
                existing.team = team
                existing.gp = gp
                existing.goals = goals
                existing.assists = assists
                existing.points = points
                existing.plus_minus = plus_minus
                existing.pim = pim
                existing.shots = shots
                existing.shootpct = shooting_pct
                updated_count += 1
            else:
                new_stats = BasicPlayerStats(
                    player_id=player.id,
                    contract_id=contract.id,
                    season=season_int,
                    playoff=playoff,
                    team=team,
                    gp=gp,
                    goals=goals,
                    assists=assists,
                    points=points,
                    plus_minus=plus_minus,
                    pim=pim,
                    shots=shots,
                    shootpct=shooting_pct
                )
                db.add(new_stats)
                created_count += 1
            
            if (created_count + updated_count) % 100 == 0:
                db.commit()
        
        db.commit()
        
    except Exception as e:
        db.rollback()
        traceback.print_exc()
    finally:
        db.close()



    
def main():
    get_skater_stats()
    get_goalie_stats()
    

