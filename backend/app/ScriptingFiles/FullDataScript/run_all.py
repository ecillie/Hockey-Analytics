"""Run the complete schema-native ingestion pipeline."""

import json
import logging

from app.ScriptingFiles.FullDataScript.ingestion import run_all
from app.ScriptingFiles.FullDataScript.populate_roster_status import main as populate_roster_status


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    summary = run_all()
    roster_exit_code = populate_roster_status()
    if roster_exit_code != 0:
        raise RuntimeError(
            f"Roster-status population finished with exit code {roster_exit_code}"
        )
    print(json.dumps(summary, indent=2, sort_keys=True))

if __name__ == "__main__":
    main()
