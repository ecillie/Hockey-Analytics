"""Grab all active players from CapWages and save them to the database"""
import sys
import os
import traceback

import requests
import json
import re
from sqlalchemy.orm import Session
from app.database import SessionLocal, init_db
from app.models import Player

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

headers = {
    "User-Agent": "EvanTradeValueProject/1.0 (contact: your_email@example.com)",
    "Accept": "text/html,application/json",
}


def parse_name(full_name: str):
    """Takes a full name and splits it into first and last name"""
    if not full_name or full_name == 'N/A':
        return "Unknown", "Unknown"
    
    full_name = full_name.strip()
    
    if ',' in full_name:
        parts = [p.strip() for p in full_name.split(',', 1)]
        if len(parts) == 2:
            return parts[1], parts[0]
    
    parts = full_name.split()
    if len(parts) >= 2:
        firstname = parts[0]
        lastname = ' '.join(parts[1:])
        return firstname, lastname
    elif len(parts) == 1:
        return parts[0], "Unknown"
    else:
        return "Unknown", "Unknown"


def scrape_all_players():
    """Fetches all active players from the CapWages active players page"""
    url = "https://capwages.com/players/active"
    resp = requests.get(url, headers=headers)   

    try:
        html = resp.text
        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            html,
            re.DOTALL
        )
        if match:
            json_str = match.group(1)
            data = json.loads(json_str)
            if 'props' in data and 'pageProps' in data['props']:
                page_props = data['props']['pageProps']
                players_array = page_props.get('playersArray', [])
                players = []
                for player_data in players_array:
                    if isinstance(player_data, list) and len(player_data) >= 4:
                        full_name = player_data[0] if len(player_data) > 0 else 'N/A'
                        firstname, lastname = parse_name(full_name)
                        
                        players.append({
                            'firstname': firstname,
                            'lastname': lastname,
                            'team': player_data[2] if len(player_data) > 2 else 'N/A',
                            'position': player_data[3] if len(player_data) > 3 else 'N/A',
                            'age': player_data[8] if len(player_data) > 8 else None,
                        })
                return players
    except Exception as e:
        traceback.print_exc()
        return []


def save_players_to_db(players: list):
    """Saves all the scraped players to the database, updating existing ones if they're already there"""
    init_db()
    
    db: Session = SessionLocal()
    try:
        created_count = 0
        updated_count = 0
        skipped_count = 0
        
        for player_data in players:
            if (not player_data.get('firstname') or 
                not player_data.get('lastname') or
                player_data.get('team') == 'N/A' or
                player_data.get('position') == 'N/A' or
                player_data.get('age') is None or
                player_data.get('age') == 'N/A'):
                skipped_count += 1
                continue
            
            existing_player = db.query(Player).filter(
                Player.firstname == player_data['firstname'],
                Player.lastname == player_data['lastname'],
                Player.team == player_data['team']
            ).first()
            
            if existing_player:
                existing_player.team = player_data['team']
                existing_player.position = player_data['position']
                existing_player.age = player_data['age']
                updated_count += 1
            else:
                new_player = Player(
                    firstname=player_data['firstname'],
                    lastname=player_data['lastname'],
                    team=player_data['team'],
                    position=player_data['position'],
                    age=player_data['age'],
                )
                db.add(new_player)
                created_count += 1
        
        db.commit()
        
    except Exception as e:
        db.rollback()
        traceback.print_exc()
    finally:
        db.close()


def main():
    players = scrape_all_players()    
    save_players_to_db(players)
    
