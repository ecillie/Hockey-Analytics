"""Database connections for ingestion scripts.

The schema is applied manually from backend/database/schema.sql. This module
does not call metadata.create_all() or otherwise mutate the schema.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import get_database_settings


settings = get_database_settings()
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args={"connect_timeout": settings.connect_timeout_seconds},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db() -> None:
    """Verify that the manually applied schema is reachable and present."""
    with engine.connect() as connection:
        players_table = connection.execute(
            text("SELECT to_regclass('public.players')")
        ).scalar_one()
    if players_table is None:
        raise RuntimeError(
            "Database schema is missing; apply backend/database/schema.sql first"
        )


def connect_database():
    """Return a psycopg2 connection for bulk loaders using DB-API directly."""
    try:
        import psycopg2
    except ImportError as exc:
        raise RuntimeError(
            "Database access requires psycopg2-binary; "
            "run 'pip install -r backend/requirements.txt'"
        ) from exc

    return psycopg2.connect(
        settings.database_url,
        connect_timeout=settings.connect_timeout_seconds,
    )


@contextmanager
def database_transaction() -> Iterator[object]:
    """Provide a DB-API connection that commits or rolls back atomically."""
    connection = connect_database()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
