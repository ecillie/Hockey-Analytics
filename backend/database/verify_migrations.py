"""Validate migration history invariants without changing a database."""

from __future__ import annotations

import argparse
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def validate(config_path: Path) -> list[str]:
    config = Config(str(config_path))
    scripts = ScriptDirectory.from_config(config)
    errors: list[str] = []

    heads = scripts.get_heads()
    if len(heads) != 1:
        errors.append(f"expected exactly one migration head, found {len(heads)}: {heads}")

    revisions = list(scripts.walk_revisions(base="base", head="heads"))
    if not revisions:
        errors.append("migration history is empty")
    for revision in revisions:
        if not revision.doc:
            errors.append(f"migration {revision.revision} has no description")
        if revision.is_merge_point:
            errors.append(f"migration {revision.revision} is an unapproved merge point")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "alembic.ini",
    )
    args = parser.parse_args()
    errors = validate(args.config.resolve())
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Migration history has one linear head and valid revision metadata.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
