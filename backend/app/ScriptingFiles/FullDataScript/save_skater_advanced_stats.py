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
from app.models import Player, Contract, AdvancedSkaterStats

# cd backend && DB_HOST=localhost python3 -m app.ScriptingFiles.save_skater_advanced_stats  

headers = {
    "User-Agent": "EvanTradeValueProject/1.0 (contact: your_email@example.com)",
    "Accept": "text/html,application/json",
}

def load_skater_advanced_stats_csv():
    """Loads the skater advanced stats from the CSV file and saves them to the database"""
    
    all_dataframes = []
    
    
    file_name = "skaters_2008_to_2024.csv"
    file_path = os.path.join(
        os.path.dirname(__file__), '..', 'data', 'skater advanced', file_name
    )
    if os.path.exists(file_path):
        try:
            df = pd.read_csv(file_path)
            all_dataframes.append(df)
        except Exception as e:
            return pd.DataFrame()
        url = "https://moneypuck.com/moneypuck/playerData/seasonSummary/2025/regular/skaters.csv"
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

def convert_to_decimal(value):
    """Converts value to Decimal if not NaN, otherwise None"""
    if pd.isna(value):
        return None
    try:
        return Decimal(str(value))
    except:
        return None

def convert_to_int(value):
    """Converts value to int if not NaN, otherwise None"""
    if pd.isna(value):
        return None
    try:
        return int(float(value))
    except:
        return None

def save_skater_advanced_stats_to_db(df):
    """Saves the skater advanced stats to the database"""
    if df.empty:
        print("No data to save")
        return
    
    init_db()
    db: Session = SessionLocal()
    try:
        created_count = 0
        updated_count = 0
        skipped_count = 0
        
        for index, row in df.iterrows():
            # Parse player name
            full_name = row.get('name', '')
            firstname, lastname = parse_player_name(full_name)
            
            if not firstname or not lastname:
                skipped_count += 1
                continue
            
            season_int = int(row.get('season'))
            team = str(row.get('team', ''))
            
            # Handle duplicate player names by matching with team and contract
            players = db.query(Player).filter(
                Player.firstname.ilike(firstname),
                Player.lastname.ilike(lastname)
            ).all()
            
            if not players:
                skipped_count += 1
                continue
            
            # Try to find the correct player by matching contract and team
            player = None
            contract = None
            
            # First, try to find a player with a contract for this season where contract team matches CSV team
            for candidate_player in players:
                candidate_contract = db.query(Contract).filter(
                    Contract.player_id == candidate_player.id,
                    Contract.start_year <= season_int,
                    Contract.end_year >= season_int,
                    Contract.team.ilike(team)
                ).first()
                
                if candidate_contract:
                    player = candidate_player
                    contract = candidate_contract
                    break
            
            # If no match with team, try without team constraint (fallback)
            if not player:
                matching_contracts = []
                for candidate_player in players:
                    candidate_contract = db.query(Contract).filter(
                        Contract.player_id == candidate_player.id,
                        Contract.start_year <= season_int,
                        Contract.end_year >= season_int
                    ).first()
                    
                    if candidate_contract:
                        matching_contracts.append((candidate_player, candidate_contract))
                
                # If only one player has a matching contract, use it
                if len(matching_contracts) == 1:
                    player, contract = matching_contracts[0]
                # If multiple players have contracts, skip to avoid ambiguity
                elif len(matching_contracts) > 1:
                    skipped_count += 1
                    continue
            
            if not player or not contract:
                skipped_count += 1
                continue
            
            playoff = False
            situation = str(row.get('situation', ''))
            
            existing = db.query(AdvancedSkaterStats).filter(
                AdvancedSkaterStats.player_id == player.id,
                AdvancedSkaterStats.contract_id == contract.id,
                AdvancedSkaterStats.season == season_int,
                AdvancedSkaterStats.playoff == playoff,
                AdvancedSkaterStats.situation == situation
            ).first()
            
            def get_csv_value(csv_col):
                val = row.get(csv_col)
                if pd.isna(val):
                    return None
                return val
            
            stats_data = {
                'player_id': player.id,
                'contract_id': contract.id,
                'season': season_int,
                'playoff': playoff,
                'team': team,
                'situation': situation,
                
                # Basic game info
                'games_played': convert_to_int(get_csv_value('games_played')),
                'icetime': convert_to_decimal(get_csv_value('icetime')),
                'shifts': convert_to_int(get_csv_value('shifts')),
                'game_score': convert_to_decimal(get_csv_value('gameScore')),
                
                # On/Off ice percentages
                'on_ice_x_goals_percentage': convert_to_decimal(get_csv_value('onIce_xGoalsPercentage')),
                'off_ice_x_goals_percentage': convert_to_decimal(get_csv_value('offIce_xGoalsPercentage')),
                'on_ice_corsi_percentage': convert_to_decimal(get_csv_value('onIce_corsiPercentage')),
                'off_ice_corsi_percentage': convert_to_decimal(get_csv_value('offIce_corsiPercentage')),
                'on_ice_fenwick_percentage': convert_to_decimal(get_csv_value('onIce_fenwickPercentage')),
                'off_ice_fenwick_percentage': convert_to_decimal(get_csv_value('offIce_fenwickPercentage')),
                'ice_time_rank': convert_to_int(get_csv_value('iceTimeRank')),
                
                # Individual For (I_F_) stats
                'i_f_x_on_goal': convert_to_decimal(get_csv_value('I_F_xOnGoal')),
                'i_f_x_goals': convert_to_decimal(get_csv_value('I_F_xGoals')),
                'i_f_x_rebounds': convert_to_decimal(get_csv_value('I_F_xRebounds')),
                'i_f_x_freeze': convert_to_decimal(get_csv_value('I_F_xFreeze')),
                'i_f_x_play_stopped': convert_to_decimal(get_csv_value('I_F_xPlayStopped')),
                'i_f_x_play_continued_in_zone': convert_to_decimal(get_csv_value('I_F_xPlayContinuedInZone')),
                'i_f_x_play_continued_outside_zone': convert_to_decimal(get_csv_value('I_F_xPlayContinuedOutsideZone')),
                'i_f_flurry_adjusted_x_goals': convert_to_decimal(get_csv_value('I_F_flurryAdjustedxGoals')),
                'i_f_score_venue_adjusted_x_goals': convert_to_decimal(get_csv_value('I_F_scoreVenueAdjustedxGoals')),
                'i_f_flurry_score_venue_adjusted_x_goals': convert_to_decimal(get_csv_value('I_F_flurryScoreVenueAdjustedxGoals')),
                'i_f_primary_assists': convert_to_int(get_csv_value('I_F_primaryAssists')),
                'i_f_secondary_assists': convert_to_int(get_csv_value('I_F_secondaryAssists')),
                'i_f_shots_on_goal': convert_to_int(get_csv_value('I_F_shotsOnGoal')),
                'i_f_missed_shots': convert_to_int(get_csv_value('I_F_missedShots')),
                'i_f_blocked_shot_attempts': convert_to_int(get_csv_value('I_F_blockedShotAttempts')),
                'i_f_shot_attempts': convert_to_int(get_csv_value('I_F_shotAttempts')),
                'i_f_points': convert_to_int(get_csv_value('I_F_points')),
                'i_f_goals': convert_to_int(get_csv_value('I_F_goals')),
                'i_f_rebounds': convert_to_int(get_csv_value('I_F_rebounds')),
                'i_f_rebound_goals': convert_to_int(get_csv_value('I_F_reboundGoals')),
                'i_f_freeze': convert_to_int(get_csv_value('I_F_freeze')),
                'i_f_play_stopped': convert_to_int(get_csv_value('I_F_playStopped')),
                'i_f_play_continued_in_zone': convert_to_int(get_csv_value('I_F_playContinuedInZone')),
                'i_f_play_continued_outside_zone': convert_to_int(get_csv_value('I_F_playContinuedOutsideZone')),
                'i_f_saved_shots_on_goal': convert_to_int(get_csv_value('I_F_savedShotsOnGoal')),
                'i_f_saved_unblocked_shot_attempts': convert_to_int(get_csv_value('I_F_savedUnblockedShotAttempts')),
                'i_f_penalties': convert_to_int(get_csv_value('penalties')),
                'i_f_penalty_minutes': convert_to_int(get_csv_value('I_F_penalityMinutes')),
                'i_f_faceoffs_won': convert_to_int(get_csv_value('I_F_faceOffsWon')),
                'i_f_hits': convert_to_int(get_csv_value('I_F_hits')),
                'i_f_takeaways': convert_to_int(get_csv_value('I_F_takeaways')),
                'i_f_giveaways': convert_to_int(get_csv_value('I_F_giveaways')),
                'i_f_low_danger_shots': convert_to_int(get_csv_value('I_F_lowDangerShots')),
                'i_f_medium_danger_shots': convert_to_int(get_csv_value('I_F_mediumDangerShots')),
                'i_f_high_danger_shots': convert_to_int(get_csv_value('I_F_highDangerShots')),
                'i_f_low_danger_x_goals': convert_to_decimal(get_csv_value('I_F_lowDangerxGoals')),
                'i_f_medium_danger_x_goals': convert_to_decimal(get_csv_value('I_F_mediumDangerxGoals')),
                'i_f_high_danger_x_goals': convert_to_decimal(get_csv_value('I_F_highDangerxGoals')),
                'i_f_low_danger_goals': convert_to_int(get_csv_value('I_F_lowDangerGoals')),
                'i_f_medium_danger_goals': convert_to_int(get_csv_value('I_F_mediumDangerGoals')),
                'i_f_high_danger_goals': convert_to_int(get_csv_value('I_F_highDangerGoals')),
                'i_f_score_adjusted_shot_attempts': convert_to_int(get_csv_value('I_F_scoreAdjustedShotsAttempts')),
                'i_f_unblocked_shot_attempts': convert_to_int(get_csv_value('I_F_unblockedShotAttempts')),
                'i_f_score_adjusted_unblocked_shot_attempts': convert_to_int(get_csv_value('I_F_scoreAdjustedUnblockedShotAttempts')),
                'i_f_d_zone_giveaways': convert_to_int(get_csv_value('I_F_dZoneGiveaways')),
                'i_f_x_goals_from_x_rebounds_of_shots': convert_to_decimal(get_csv_value('I_F_xGoalsFromxReboundsOfShots')),
                'i_f_x_goals_from_actual_rebounds_of_shots': convert_to_decimal(get_csv_value('I_F_xGoalsFromActualReboundsOfShots')),
                'i_f_rebound_x_goals': convert_to_decimal(get_csv_value('I_F_reboundxGoals')),
                'i_f_x_goals_with_earned_rebounds': convert_to_decimal(get_csv_value('I_F_xGoals_with_earned_rebounds')),
                'i_f_x_goals_with_earned_rebounds_score_adjusted': convert_to_decimal(get_csv_value('I_F_xGoals_with_earned_rebounds_scoreAdjusted')),
                'i_f_x_goals_with_earned_rebounds_score_flurry_adjusted': convert_to_decimal(get_csv_value('I_F_xGoals_with_earned_rebounds_scoreFlurryAdjusted')),
                'i_f_shifts': convert_to_int(get_csv_value('I_F_shifts')),
                'i_f_o_zone_shift_starts': convert_to_int(get_csv_value('I_F_oZoneShiftStarts')),
                'i_f_d_zone_shift_starts': convert_to_int(get_csv_value('I_F_dZoneShiftStarts')),
                'i_f_neutral_zone_shift_starts': convert_to_int(get_csv_value('I_F_neutralZoneShiftStarts')),
                'i_f_fly_shift_starts': convert_to_int(get_csv_value('I_F_flyShiftStarts')),
                'i_f_o_zone_shift_ends': convert_to_int(get_csv_value('I_F_oZoneShiftEnds')),
                'i_f_d_zone_shift_ends': convert_to_int(get_csv_value('I_F_dZoneShiftEnds')),
                'i_f_neutral_zone_shift_ends': convert_to_int(get_csv_value('I_F_neutralZoneShiftEnds')),
                'i_f_fly_shift_ends': convert_to_int(get_csv_value('I_F_flyShiftEnds')),
                
                # Faceoffs and other stats
                'faceoffs_won': convert_to_int(get_csv_value('faceoffsWon')),
                'faceoffs_lost': convert_to_int(get_csv_value('faceoffsLost')),
                'time_on_bench': convert_to_int(get_csv_value('timeOnBench')),
                'penalty_minutes': convert_to_int(get_csv_value('penalityMinutes')),
                'penalty_minutes_drawn': convert_to_int(get_csv_value('penalityMinutesDrawn')),
                'penalties_drawn': convert_to_int(get_csv_value('penaltiesDrawn')),
                'shots_blocked_by_player': convert_to_int(get_csv_value('shotsBlockedByPlayer')),
                
                # OnIce For (OnIce_F_) stats
                'on_ice_f_x_on_goal': convert_to_decimal(get_csv_value('OnIce_F_xOnGoal')),
                'on_ice_f_x_goals': convert_to_decimal(get_csv_value('OnIce_F_xGoals')),
                'on_ice_f_flurry_adjusted_x_goals': convert_to_decimal(get_csv_value('OnIce_F_flurryAdjustedxGoals')),
                'on_ice_f_score_venue_adjusted_x_goals': convert_to_decimal(get_csv_value('OnIce_F_scoreVenueAdjustedxGoals')),
                'on_ice_f_flurry_score_venue_adjusted_x_goals': convert_to_decimal(get_csv_value('OnIce_F_flurryScoreVenueAdjustedxGoals')),
                'on_ice_f_shots_on_goal': convert_to_int(get_csv_value('OnIce_F_shotsOnGoal')),
                'on_ice_f_missed_shots': convert_to_int(get_csv_value('OnIce_F_missedShots')),
                'on_ice_f_blocked_shot_attempts': convert_to_int(get_csv_value('OnIce_F_blockedShotAttempts')),
                'on_ice_f_shot_attempts': convert_to_int(get_csv_value('OnIce_F_shotAttempts')),
                'on_ice_f_goals': convert_to_int(get_csv_value('OnIce_F_goals')),
                'on_ice_f_rebounds': convert_to_int(get_csv_value('OnIce_F_rebounds')),
                'on_ice_f_rebound_goals': convert_to_int(get_csv_value('OnIce_F_reboundGoals')),
                'on_ice_f_low_danger_shots': convert_to_int(get_csv_value('OnIce_F_lowDangerShots')),
                'on_ice_f_medium_danger_shots': convert_to_int(get_csv_value('OnIce_F_mediumDangerShots')),
                'on_ice_f_high_danger_shots': convert_to_int(get_csv_value('OnIce_F_highDangerShots')),
                'on_ice_f_low_danger_x_goals': convert_to_decimal(get_csv_value('OnIce_F_lowDangerxGoals')),
                'on_ice_f_medium_danger_x_goals': convert_to_decimal(get_csv_value('OnIce_F_mediumDangerxGoals')),
                'on_ice_f_high_danger_x_goals': convert_to_decimal(get_csv_value('OnIce_F_highDangerxGoals')),
                'on_ice_f_low_danger_goals': convert_to_int(get_csv_value('OnIce_F_lowDangerGoals')),
                'on_ice_f_medium_danger_goals': convert_to_int(get_csv_value('OnIce_F_mediumDangerGoals')),
                'on_ice_f_high_danger_goals': convert_to_int(get_csv_value('OnIce_F_highDangerGoals')),
                'on_ice_f_score_adjusted_shot_attempts': convert_to_int(get_csv_value('OnIce_F_scoreAdjustedShotsAttempts')),
                'on_ice_f_unblocked_shot_attempts': convert_to_int(get_csv_value('OnIce_F_unblockedShotAttempts')),
                'on_ice_f_score_adjusted_unblocked_shot_attempts': convert_to_int(get_csv_value('OnIce_F_scoreAdjustedUnblockedShotAttempts')),
                'on_ice_f_x_goals_from_x_rebounds_of_shots': convert_to_decimal(get_csv_value('OnIce_F_xGoalsFromxReboundsOfShots')),
                'on_ice_f_x_goals_from_actual_rebounds_of_shots': convert_to_decimal(get_csv_value('OnIce_F_xGoalsFromActualReboundsOfShots')),
                'on_ice_f_rebound_x_goals': convert_to_decimal(get_csv_value('OnIce_F_reboundxGoals')),
                'on_ice_f_x_goals_with_earned_rebounds': convert_to_decimal(get_csv_value('OnIce_F_xGoals_with_earned_rebounds')),
                'on_ice_f_x_goals_with_earned_rebounds_score_adjusted': convert_to_decimal(get_csv_value('OnIce_F_xGoals_with_earned_rebounds_scoreAdjusted')),
                'on_ice_f_x_goals_with_earned_rebounds_score_flurry_adjusted': convert_to_decimal(get_csv_value('OnIce_F_xGoals_with_earned_rebounds_scoreFlurryAdjusted')),
                
                # OnIce Against (OnIce_A_) stats
                'on_ice_a_x_on_goal': convert_to_decimal(get_csv_value('OnIce_A_xOnGoal')),
                'on_ice_a_x_goals': convert_to_decimal(get_csv_value('OnIce_A_xGoals')),
                'on_ice_a_flurry_adjusted_x_goals': convert_to_decimal(get_csv_value('OnIce_A_flurryAdjustedxGoals')),
                'on_ice_a_score_venue_adjusted_x_goals': convert_to_decimal(get_csv_value('OnIce_A_scoreVenueAdjustedxGoals')),
                'on_ice_a_flurry_score_venue_adjusted_x_goals': convert_to_decimal(get_csv_value('OnIce_A_flurryScoreVenueAdjustedxGoals')),
                'on_ice_a_shots_on_goal': convert_to_int(get_csv_value('OnIce_A_shotsOnGoal')),
                'on_ice_a_missed_shots': convert_to_int(get_csv_value('OnIce_A_missedShots')),
                'on_ice_a_blocked_shot_attempts': convert_to_int(get_csv_value('OnIce_A_blockedShotAttempts')),
                'on_ice_a_shot_attempts': convert_to_int(get_csv_value('OnIce_A_shotAttempts')),
                'on_ice_a_goals': convert_to_int(get_csv_value('OnIce_A_goals')),
                'on_ice_a_rebounds': convert_to_int(get_csv_value('OnIce_A_rebounds')),
                'on_ice_a_rebound_goals': convert_to_int(get_csv_value('OnIce_A_reboundGoals')),
                'on_ice_a_low_danger_shots': convert_to_int(get_csv_value('OnIce_A_lowDangerShots')),
                'on_ice_a_medium_danger_shots': convert_to_int(get_csv_value('OnIce_A_mediumDangerShots')),
                'on_ice_a_high_danger_shots': convert_to_int(get_csv_value('OnIce_A_highDangerShots')),
                'on_ice_a_low_danger_x_goals': convert_to_decimal(get_csv_value('OnIce_A_lowDangerxGoals')),
                'on_ice_a_medium_danger_x_goals': convert_to_decimal(get_csv_value('OnIce_A_mediumDangerxGoals')),
                'on_ice_a_high_danger_x_goals': convert_to_decimal(get_csv_value('OnIce_A_highDangerxGoals')),
                'on_ice_a_low_danger_goals': convert_to_int(get_csv_value('OnIce_A_lowDangerGoals')),
                'on_ice_a_medium_danger_goals': convert_to_int(get_csv_value('OnIce_A_mediumDangerGoals')),
                'on_ice_a_high_danger_goals': convert_to_int(get_csv_value('OnIce_A_highDangerGoals')),
                'on_ice_a_score_adjusted_shot_attempts': convert_to_int(get_csv_value('OnIce_A_scoreAdjustedShotsAttempts')),
                'on_ice_a_unblocked_shot_attempts': convert_to_int(get_csv_value('OnIce_A_unblockedShotAttempts')),
                'on_ice_a_score_adjusted_unblocked_shot_attempts': convert_to_int(get_csv_value('OnIce_A_scoreAdjustedUnblockedShotAttempts')),
                'on_ice_a_x_goals_from_x_rebounds_of_shots': convert_to_decimal(get_csv_value('OnIce_A_xGoalsFromxReboundsOfShots')),
                'on_ice_a_x_goals_from_actual_rebounds_of_shots': convert_to_decimal(get_csv_value('OnIce_A_xGoalsFromActualReboundsOfShots')),
                'on_ice_a_rebound_x_goals': convert_to_decimal(get_csv_value('OnIce_A_reboundxGoals')),
                'on_ice_a_x_goals_with_earned_rebounds': convert_to_decimal(get_csv_value('OnIce_A_xGoals_with_earned_rebounds')),
                'on_ice_a_x_goals_with_earned_rebounds_score_adjusted': convert_to_decimal(get_csv_value('OnIce_A_xGoals_with_earned_rebounds_scoreAdjusted')),
                'on_ice_a_x_goals_with_earned_rebounds_score_flurry_adjusted': convert_to_decimal(get_csv_value('OnIce_A_xGoals_with_earned_rebounds_scoreFlurryAdjusted')),
                
                # OffIce stats
                'off_ice_f_x_goals': convert_to_decimal(get_csv_value('OffIce_F_xGoals')),
                'off_ice_a_x_goals': convert_to_decimal(get_csv_value('OffIce_A_xGoals')),
                'off_ice_f_shot_attempts': convert_to_int(get_csv_value('OffIce_F_shotAttempts')),
                'off_ice_a_shot_attempts': convert_to_int(get_csv_value('OffIce_A_shotAttempts')),
                
                # After shift stats
                'x_goals_for_after_shifts': convert_to_decimal(get_csv_value('xGoalsForAfterShifts')),
                'x_goals_against_after_shifts': convert_to_decimal(get_csv_value('xGoalsAgainstAfterShifts')),
                'corsi_for_after_shifts': convert_to_int(get_csv_value('corsiForAfterShifts')),
                'corsi_against_after_shifts': convert_to_int(get_csv_value('corsiAgainstAfterShifts')),
                'fenwick_for_after_shifts': convert_to_int(get_csv_value('fenwickForAfterShifts')),
                'fenwick_against_after_shifts': convert_to_int(get_csv_value('fenwickAgainstAfterShifts')),
            }
            
            if existing:
                for key, value in stats_data.items():
                    if key not in ['player_id', 'contract_id', 'season', 'playoff', 'situation']:
                        setattr(existing, key, value)
                updated_count += 1
            else:
                new_stats = AdvancedSkaterStats(**stats_data)
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
    df = load_skater_advanced_stats_csv()
    save_skater_advanced_stats_to_db(df)
   
