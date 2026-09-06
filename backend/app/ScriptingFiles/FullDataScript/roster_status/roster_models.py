"""Shared data types for full-load roster ingestion and classification."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Generic, TypeVar


class RosterStatus(str, Enum):
    ACTIVE = "ACTIVE"
    MINORS = "MINORS"
    LTIR = "LTIR"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ExternalRosterPlayer:
    external_id: str
    full_name: str
    birth_date: date | None = None
    team_external_id: str | None = None


@dataclass(frozen=True)
class StoredPlayer:
    id: int
    first_name: str
    last_name: str
    birth_date: date | None
    roster_status: RosterStatus
    nhl_external_id: str | None = None
    ahl_external_id: str | None = None

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


T = TypeVar("T")


@dataclass(frozen=True)
class FetchResult(Generic[T]):
    items: T
    complete: bool
    errors: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SyncSummary:
    statuses_updated: int
    active_count: int
    minors_count: int
    ltir_count: int
    unknown_count: int
    preserved_count: int
    nhl_complete: bool
    ahl_complete: bool
    errors: tuple[str, ...]
