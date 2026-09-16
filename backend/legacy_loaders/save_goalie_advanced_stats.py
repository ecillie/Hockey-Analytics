
import sys
import os
import traceback
import pandas as pd
import io
import requests
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from sqlalchemy.orm import Session
from decimal import Decimal

from app.database import SessionLocal, init_db
from app.models import Player, Contract, AdvancedGoalieStats

# cd backend && DB_HOST=localhost python3 -m app.ScriptingFiles.save_goalie_advanced_stats

headers = {
    "User-Agent": "EvanTradeValueProject/1.0 (contact: your_email@example.com)",
    "Accept": "text/html,application/json",
}

def load_goalie_advanced_stats_csv():
    """Loads the goalie advanced stats from the CSV file and saves them to the database"""
    
    all_dataframes = []

    file_name = "goalies_2008_to_2024.csv"
    file_path = os.path.join(
        os.path.dirname(__file__), '..', 'data', 'goalie advanced', file_name
    )
    if os.path.exists(file_path):
        try:
            df = pd.read_csv(file_path)
            all_dataframes.append(df)
        except Exception as e:
            return pd.DataFrame()
    url = "https://moneypuck.com/moneypuck/playerData/seasonSummary/2025/regular/goalies.csv"
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    all_dataframes.append(df)
    if all_dataframes:
        combined_df = pd.concat(all_dataframes, ignore_index=True)
        return combined_df
    else:
        return pd.DataFrame()

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

def save_goalie_advanced_stats_to_db(df):
    """Saves the goalie advanced stats to the database"""
    if df.empty:
        return
    
    init_db()
    db: Session = SessionLocal()
    try:
        created_count = 0
        updated_count = 0
        skipped_count = 0
        
        for index, row in df.iterrows():
            
            full_name = row.get('name', '')
            firstname, lastname = parse_player_name(full_name)
            
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
            
            season_int = int(row.get('season'))
            
            contract = db.query(Contract).filter(
                Contract.player_id == player.id,
                Contract.start_year <= season_int,
                Contract.end_year >= season_int
            ).first()
            
            if not contract:
                skipped_count += 1
                continue
            
            playoff = False
            team = str(row.get('team', ''))
            situation = str(row.get('situation', ''))
            
            existing = db.query(AdvancedGoalieStats).filter(
                AdvancedGoalieStats.player_id == player.id,
                AdvancedGoalieStats.contract_id == contract.id,
                AdvancedGoalieStats.season == season_int,
                AdvancedGoalieStats.playoff == playoff,
                AdvancedGoalieStats.situation == situation
            ).first()
            
            stats_data = {
                'player_id': player.id,
                'contract_id': contract.id,
                'season': season_int,
                'playoff': playoff,
                'team': team,
                'situation': situation,
                'icetime': Decimal(str(row.get('icetime'))) if pd.notna(row.get('icetime')) else None,
                'x_goals': Decimal(str(row.get('xGoals'))) if pd.notna(row.get('xGoals')) else None,
                'goals': Decimal(str(row.get('goals'))) if pd.notna(row.get('goals')) else None,
                'unblocked_shot_attempts': int(row.get('unblocked_shot_attempts', 0)) if pd.notna(row.get('unblocked_shot_attempts')) else None,
                'blocked_shot_attempts': int(row.get('blocked_shot_attempts', 0)) if pd.notna(row.get('blocked_shot_attempts')) else None,
                'x_rebounds': Decimal(str(row.get('xRebounds'))) if pd.notna(row.get('xRebounds')) else None,
                'rebounds': int(row.get('rebounds', 0)) if pd.notna(row.get('rebounds')) else None,
                'x_freeze': Decimal(str(row.get('xFreeze'))) if pd.notna(row.get('xFreeze')) else None,
                'act_freeze': int(row.get('freeze', 0)) if pd.notna(row.get('freeze')) else None,
                'x_on_goal': Decimal(str(row.get('xOnGoal'))) if pd.notna(row.get('xOnGoal')) else None,
                'on_goal': int(row.get('ongoal', 0)) if pd.notna(row.get('ongoal')) else None,
                'x_play_stopped': Decimal(str(row.get('xPlayStopped'))) if pd.notna(row.get('xPlayStopped')) else None,
                'play_stopped': int(row.get('playStopped', 0)) if pd.notna(row.get('playStopped')) else None,
                'x_play_continued_in_zone': Decimal(str(row.get('xPlayContinuedInZone'))) if pd.notna(row.get('xPlayContinuedInZone')) else None,
                'play_continued_in_zone': int(row.get('playContinuedInZone', 0)) if pd.notna(row.get('playContinuedInZone')) else None,
                'x_play_continued_outside_zone': Decimal(str(row.get('xPlayContinuedOutsideZone'))) if pd.notna(row.get('xPlayContinuedOutsideZone')) else None,
                'play_continued_outside_zone': int(row.get('playContinuedOutsideZone', 0)) if pd.notna(row.get('playContinuedOutsideZone')) else None,
                'flurry_adjusted_x_goals': Decimal(str(row.get('flurryAdjustedxGoals'))) if pd.notna(row.get('flurryAdjustedxGoals')) else None,
                'low_danger_shots': int(row.get('lowDangerShots', 0)) if pd.notna(row.get('lowDangerShots')) else None,
                'medium_danger_shots': int(row.get('mediumDangerShots', 0)) if pd.notna(row.get('mediumDangerShots')) else None,
                'high_danger_shots': int(row.get('highDangerShots', 0)) if pd.notna(row.get('highDangerShots')) else None,
                'low_danger_x_goals': Decimal(str(row.get('lowDangerxGoals'))) if pd.notna(row.get('lowDangerxGoals')) else None,
                'medium_danger_x_goals': Decimal(str(row.get('mediumDangerxGoals'))) if pd.notna(row.get('mediumDangerxGoals')) else None,
                'high_danger_x_goals': Decimal(str(row.get('highDangerxGoals'))) if pd.notna(row.get('highDangerxGoals')) else None,
                'low_danger_goals': int(row.get('lowDangerGoals', 0)) if pd.notna(row.get('lowDangerGoals')) else None,
                'medium_danger_goals': int(row.get('mediumDangerGoals', 0)) if pd.notna(row.get('mediumDangerGoals')) else None,
                'high_danger_goals': int(row.get('highDangerGoals', 0)) if pd.notna(row.get('highDangerGoals')) else None,
            }
            
            if existing:
                for key, value in stats_data.items():
                    if key not in ['player_id', 'contract_id', 'season', 'playoff', 'situation']:
                        setattr(existing, key, value)
                updated_count += 1
            else:
                new_stats = AdvancedGoalieStats(**stats_data)
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
    df = load_goalie_advanced_stats_csv()
    save_goalie_advanced_stats_to_db(df)
