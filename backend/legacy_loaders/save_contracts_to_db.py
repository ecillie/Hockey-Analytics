"""Grabs contract data for all players from CapWages and saves it to the database"""
import sys
import os

import requests
import json
import re
from sqlalchemy.orm import Session
from decimal import Decimal
from app.database import SessionLocal, init_db
from app.models import Player, Contract

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))) 

SALARY_CAP ={'2005' : Decimal('39000000'), '2006' : Decimal('44000000'), '2007' : Decimal('50300000'), '2008' : Decimal('56700000'), 
'2009' : Decimal('56800000'), '2010' : Decimal('59400000'), '2011' : Decimal('64300000'), '2012' : Decimal('70200000'), 
'2013' : Decimal('64300000'), '2014' : Decimal('69000000'), '2015' : Decimal('71400000'), '2016' : Decimal('73000000'),
'2017' : Decimal('75000000'), '2018' : Decimal('79500000'), '2019' : Decimal('81500000'), '2020' : Decimal('81500000'), 
'2021' : Decimal('81500000'), '2022' : Decimal('82500000'), '2023' : Decimal('82500000'), '2024' : Decimal('88000000'), '2025' : Decimal('95500000')}

headers = {
    "User-Agent": "EvanTradeValueProject/1.0 (contact: your_email@example.com)",
    "Accept": "text/html,application/json",
}

def parse_name(full_name: str):
    """Splits a full name into first and last name"""
    if not full_name or full_name == 'N/A':
        return "Unknown", "Unknown"
    
    full_name = full_name.strip()
    
    if ',' in full_name:
        parts = [p.strip() for p in full_name.split(',', 1)]
        if len(parts) == 2:
            return parts[1], parts[0]
    
    parts = full_name.split()
    if len(parts) >= 2:
        return parts[0], ' '.join(parts[1:])
    elif len(parts) == 1:
        return parts[0], "Unknown"
    else:
        return "Unknown", "Unknown"


def scrape_player_contracts(slug: str, team: str):
    """Grabs all contract info from a player's individual CapWages page"""
    if not slug or slug == '':
        return []
    
    url = f"https://capwages.com/players/{slug}"
    
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        html = resp.text
        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            html,
            re.DOTALL
        )
        if not match:
            return []
        
        json_str = match.group(1)
        data = json.loads(json_str)
        
        contracts = []
        
        if 'props' in data and 'pageProps' in data['props']:
            page_props = data['props']['pageProps']
            player_data = page_props.get('player', {})
            contracts_array = player_data.get('contracts', [])
            
            for contract_item in contracts_array:
                if not isinstance(contract_item, dict):
                    continue
                
                details = contract_item.get('details', [])
                if not details:
                    continue
                
                first_season = details[0].get('season', '')
                last_season = details[-1].get('season', '')
                
                if not first_season or not last_season:
                    continue
                
                try:
                    start_year = int(first_season.split('-')[0])
                    end_year_str = last_season.split('-')[1]
                    end_year = 2000 + int(end_year_str) if int(end_year_str) < 100 else int(end_year_str)
                except:
                    continue
                
                cap_hit_str = details[0].get('capHit', '')
                if not cap_hit_str:
                    continue
                
                try:
                    cap_hit = Decimal(cap_hit_str.replace('$', '').replace(',', ''))
                except:
                    continue
                
                contract_team = contract_item.get('signingTeam', team)
                duration = len(details)
                
                total_value_str = contract_item.get('value', '')
                total_value = None
                if total_value_str:
                    try:
                        total_value = Decimal(total_value_str.replace('$', '').replace(',', ''))
                    except:
                        pass
                
                if not total_value:
                    total_value = cap_hit * Decimal(duration)
                
                expiry_status = contract_item.get('expiryStatus', '')
                rfa = 'RFA' in str(expiry_status).upper()
                
                contract_type = contract_item.get('type', '')
                elc = 'ENTRY' in contract_type.upper() or 'ELC' in contract_type.upper()
        
                
                contract_data = {
                    'team': contract_team,
                    'start_year': start_year,
                    'end_year': end_year,
                    'duration': duration,
                    'cap_hit': cap_hit,
                    'rfa': rfa,
                    'elc': elc,
                    'total_value': total_value,
                }
                
                contracts.append(contract_data)
        
        return contracts
    except Exception as e:
        return []


def create_slug_from_name(firstname: str, lastname: str):
    """Turns a player's name into a URL-friendly slug"""
    name = f"{firstname} {lastname}".lower()
    slug = name.replace(' ', '-')
    slug = re.sub(r'[^a-z0-9\-]', '', slug)
    slug = re.sub(r'-+', '-', slug)
    slug = slug.strip('-')
    return slug


def build_slug_lookup_from_active_players():
    """Grabs all player slugs from the active players page so we can find their individual pages"""
    url = "https://capwages.com/players/active"
    resp = requests.get(url, headers=headers)
    
    slug_lookup = {}
    
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
                
                for player_data in players_array:
                    if isinstance(player_data, list) and len(player_data) >= 4:
                        full_name = player_data[0] if len(player_data) > 0 else ''
                        p_firstname, p_lastname = parse_name(full_name)
                        p_team = player_data[2] if len(player_data) > 2 else ''
                        slug = player_data[1] if len(player_data) > 1 else ''
                        
                        if slug:
                            key = f"{p_firstname.lower()}_{p_lastname.lower()}_{p_team}"
                            slug_lookup[key] = slug
    except Exception as e:
        pass
    
    return slug_lookup


def save_contracts_to_db():
    """Goes through all players in the database and grabs their contract info from CapWages"""
    init_db()
    
    db: Session = SessionLocal()
    try:
        all_players = db.query(Player).all()
        slug_lookup = build_slug_lookup_from_active_players()
        
        contracts_created = 0
        contracts_updated = 0
        players_without_slugs = 0
        players_processed = 0
        players_no_contracts = 0
        
        for idx, player in enumerate(all_players):
            lookup_key = f"{player.firstname.lower()}_{player.lastname.lower()}_{player.team}"
            slug = slug_lookup.get(lookup_key)
            
            if not slug:
                slug = create_slug_from_name(player.firstname, player.lastname)
                players_without_slugs += 1
            
            if not slug:
                continue
            
            contracts = scrape_player_contracts(slug, player.team)
            
            if not contracts:
                players_no_contracts += 1
                continue
            
            for contract_data in contracts:
                existing_contract = db.query(Contract).filter(
                    Contract.player_id == player.id,
                    Contract.start_year == contract_data['start_year'],
                    Contract.end_year == contract_data['end_year']
                ).first()
                
                if existing_contract:
                    existing_contract.team = contract_data['team']
                    existing_contract.duration = contract_data['duration']
                    existing_contract.cap_hit = contract_data['cap_hit']
                    existing_contract.rfa = contract_data['rfa']
                    existing_contract.elc = contract_data['elc']
                    existing_contract.total_value = contract_data['total_value']
                    contracts_updated += 1
                else:
                    new_contract = Contract(
                        player_id=player.id,
                        team=contract_data['team'],
                        start_year=contract_data['start_year'],
                        end_year=contract_data['end_year'],
                        duration=contract_data['duration'],
                        cap_hit=contract_data['cap_hit'],
                        rfa=contract_data['rfa'],
                        elc=contract_data['elc'],
                        total_value=contract_data['total_value'],
                    )
                    db.add(new_contract)
                    contracts_created += 1
            
            players_processed += 1
            db.commit()
        

        
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
    finally:
        db.close()


def main():
    save_contracts_to_db()

