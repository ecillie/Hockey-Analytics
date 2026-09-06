from app.ScriptingFiles.FullDataScript.save_basic_player_stats import main as save_basic_player_stats
from app.ScriptingFiles.FullDataScript.save_contracts_to_db import main as save_contracts_to_db
from app.ScriptingFiles.FullDataScript.save_goalie_advanced_stats import main as save_goalie_advanced_stats
from app.ScriptingFiles.FullDataScript.save_players_to_db import main as save_players_to_db
from app.ScriptingFiles.FullDataScript.save_skater_advanced_stats import main as save_skater_advanced_stats
from app.ScriptingFiles.FullDataScript.save_individual_contract_years import main as save_individual_contract_years
from app.ScriptingFiles.FullDataScript.populate_roster_status import main as populate_roster_status


def main():
    save_players_to_db()
    save_contracts_to_db()
    save_individual_contract_years()
    save_basic_player_stats()
    save_goalie_advanced_stats()
    save_skater_advanced_stats()
    roster_exit_code = populate_roster_status()
    if roster_exit_code != 0:
        raise RuntimeError(
            f"Roster-status population finished with exit code {roster_exit_code}"
        )

if __name__ == "__main__":
    main()
