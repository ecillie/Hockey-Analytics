import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import requests
import pandas as pd


def get_regular_season_games():
    date = "2026-10-01"
    games = {}

    while date:
        response = requests.get(
            f"https://api-web.nhle.com/v1/schedule/{date}"
        )
        response.raise_for_status()

        data = response.json()

        for day in data.get("gameWeek", []):
            for game in day.get("games", []):
                if game.get("gameType") == 2:
                    games[game["id"]] = {
                        "game_id": game["id"],
                        "date": game["gameDate"],
                        "start_time_utc": game["startTimeUTC"],
                        "away_team": game["awayTeam"]["abbrev"],
                        "home_team": game["homeTeam"]["abbrev"],
                        "venue": game.get("venue", {}).get("default"),
                        "game_state": game.get("gameState"),
                    }

        next_date = data.get("nextStartDate")

        if not next_date or next_date <= date:
            break

        date = next_date

    df = pd.DataFrame(games.values())

    if not df.empty:
        df = (
            df.sort_values(["date", "start_time_utc"])
            .reset_index(drop=True)
        )

    return df

def save_games_to_db ():
    pass