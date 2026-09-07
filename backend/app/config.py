"""Environment-backed configuration for the revamped backend."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
import os
from pathlib import Path
from urllib.parse import quote


BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BACKEND_DIR / ".env"


class ConfigurationError(RuntimeError):
    """Raised when required backend configuration is missing or invalid."""


class AppEnvironment(str, Enum):
    DEV = "dev"
    NONPROD = "nonprod"
    PROD = "prod"


def _load_backend_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError as exc:
        if ENV_FILE.exists():
            raise ConfigurationError(
                "backend/.env exists but python-dotenv is not installed; "
                "run 'pip install -r backend/requirements.txt'"
            ) from exc
        return

    # Exported environment variables take precedence over backend/.env.
    load_dotenv(ENV_FILE, override=False)


@dataclass(frozen=True)
class DatabaseSettings:
    environment: AppEnvironment
    database_url: str
    connect_timeout_seconds: int = 10


@dataclass(frozen=True)
class ApiSettings:
    cors_origins: tuple[str, ...]


@lru_cache(maxsize=1)
def get_api_settings() -> ApiSettings:
    """Return HTTP settings without requiring database configuration."""
    _load_backend_env()
    raw_origins = os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    )
    origins = tuple(origin.strip() for origin in raw_origins.split(",") if origin.strip())
    if not origins:
        raise ConfigurationError("CORS_ORIGINS must contain at least one origin")
    return ApiSettings(cors_origins=origins)


@lru_cache(maxsize=1)
def get_database_settings() -> DatabaseSettings:
    _load_backend_env()

    environment_text = os.getenv("ENV", "").strip().lower()
    try:
        environment = AppEnvironment(environment_text)
    except ValueError as exc:
        raise ConfigurationError("ENV must be one of: dev, nonprod, prod") from exc

    scoped_url_name = f"{environment.value.upper()}_DATABASE_URL"
    database_url = os.getenv(scoped_url_name, "").strip()
    if not database_url:
        database_url = os.getenv("DATABASE_URL", "").strip()

    if not database_url and environment is AppEnvironment.DEV:
        user = os.getenv("DB_USER", "").strip()
        database = os.getenv("DB_NAME", "").strip()
        if not user or not database:
            raise ConfigurationError(
                "For ENV=dev, set DEV_DATABASE_URL, DATABASE_URL, or both "
                "DB_USER and DB_NAME in backend/.env"
            )

        password = os.getenv("DB_PASSWORD", "")
        host = os.getenv("DB_HOST", "localhost").strip() or "localhost"
        port_text = os.getenv("DB_PORT", "5432").strip() or "5432"
        try:
            port = int(port_text)
        except ValueError as exc:
            raise ConfigurationError("DB_PORT must be an integer") from exc
        if not 1 <= port <= 65535:
            raise ConfigurationError("DB_PORT must be between 1 and 65535")

        credentials = quote(user, safe="")
        if password:
            credentials += f":{quote(password, safe='')}"
        database_url = (
            f"postgresql://{credentials}@{host}:{port}/{quote(database, safe='')}"
        )
    elif not database_url:
        raise ConfigurationError(
            f"For ENV={environment.value}, set {scoped_url_name} or DATABASE_URL "
            "in the deployment environment"
        )

    timeout_text = os.getenv("DB_CONNECT_TIMEOUT", "10").strip() or "10"
    try:
        timeout = int(timeout_text)
    except ValueError as exc:
        raise ConfigurationError("DB_CONNECT_TIMEOUT must be an integer") from exc
    if timeout <= 0:
        raise ConfigurationError("DB_CONNECT_TIMEOUT must be positive")

    return DatabaseSettings(
        environment=environment,
        database_url=database_url,
        connect_timeout_seconds=timeout,
    )
