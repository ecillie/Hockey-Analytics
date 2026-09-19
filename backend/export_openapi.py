"""Export or validate the committed OpenAPI contract without a live database."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
DEFAULT_OUTPUT = ROOT / "docs" / "openapi.json"


def _schema_text() -> str:
    # Importing the ASGI application constructs the SQLAlchemy engine but does
    # not connect. These inert defaults keep contract generation independent of
    # developer secrets and hosted infrastructure.
    os.environ["ENV"] = "dev"
    os.environ["DEV_DATABASE_URL"] = (
        "postgresql://openapi:openapi@127.0.0.1:9/openapi"
    )
    sys.path.insert(0, str(BACKEND))

    from app.main import app

    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    rendered = _schema_text()

    if args.check:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != rendered:
            print(
                f"{args.output} is stale; run `python backend/export_openapi.py`.",
                file=sys.stderr,
            )
            return 1
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(f"Wrote {args.output.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
