"""Create or verify a deterministic PostgreSQL schema-catalog snapshot."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sqlalchemy import create_engine, text


CATALOG_QUERIES = {
    "tables": """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_type = 'BASE TABLE'
          AND table_name <> 'alembic_version'
        ORDER BY table_name
    """,
    "columns": """
        SELECT table_name, ordinal_position, column_name, data_type, udt_name,
               is_nullable, column_default, is_identity, identity_generation
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name <> 'alembic_version'
        ORDER BY table_name, ordinal_position
    """,
    "constraints": """
        SELECT c.relname AS table_name, con.conname AS constraint_name,
               con.contype AS constraint_type,
               pg_get_constraintdef(con.oid, true) AS definition
        FROM pg_constraint con
        JOIN pg_class c ON c.oid = con.conrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relname <> 'alembic_version'
        ORDER BY c.relname, con.conname
    """,
    "indexes": """
        SELECT tablename AS table_name, indexname AS index_name, indexdef AS definition
        FROM pg_indexes
        WHERE schemaname = 'public' AND tablename <> 'alembic_version'
        ORDER BY tablename, indexname
    """,
    "enums": """
        SELECT t.typname AS enum_name, e.enumsortorder::int AS sort_order,
               e.enumlabel AS value
        FROM pg_type t
        JOIN pg_enum e ON e.enumtypid = t.oid
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE n.nspname = 'public'
        ORDER BY t.typname, e.enumsortorder
    """,
}


def database_url() -> str:
    url = os.getenv("DATABASE_URL") or os.getenv("TEST_DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL or TEST_DATABASE_URL is required")
    return url


def snapshot() -> dict[str, list[dict[str, object]]]:
    engine = create_engine(database_url(), pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            return {
                name: [dict(row) for row in connection.execute(text(query)).mappings()]
                for name, query in CATALOG_QUERIES.items()
            }
    finally:
        engine.dispose()


def render(value: dict[str, list[dict[str, object]]]) -> str:
    return json.dumps(value, indent=2, sort_keys=True, default=str) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--expected",
        type=Path,
        default=Path(__file__).with_name("schema.snapshot.json"),
    )
    parser.add_argument("--actual", type=Path)
    parser.add_argument("--update", action="store_true")
    args = parser.parse_args()

    actual = render(snapshot())
    if args.actual:
        args.actual.parent.mkdir(parents=True, exist_ok=True)
        args.actual.write_text(actual, encoding="utf-8")
    if args.update:
        args.expected.write_text(actual, encoding="utf-8")
        print(f"Updated {args.expected}")
        return 0
    if not args.expected.exists():
        print(f"ERROR: schema snapshot is missing: {args.expected}")
        return 1
    expected = args.expected.read_text(encoding="utf-8")
    if actual != expected:
        print("ERROR: migrated database does not match schema.snapshot.json")
        print("Run schema_snapshot.py --update only after reviewing the migration.")
        return 1
    print("Migrated database matches the committed schema snapshot.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
