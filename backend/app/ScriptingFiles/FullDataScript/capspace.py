"""Gap-driven historical NHL contract ingestion from CapSpace and CapWages.

The normal CapWages refresh starts from its active-player index. This module
fills the resulting historical gaps by selecting players from NHL stats and
querying CapSpace directly by NHL ID, then trying identity-validated CapWages
profiles when CapSpace cannot cover a requested season. Parsing and money
normalisation are deliberately independent of PostgreSQL so saved source pages
can be regression-tested without network access.
"""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, replace
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from html.parser import HTMLParser
import argparse
import hashlib
import json
import re
import time
from typing import Any, Iterable

import requests
from psycopg2.extras import Json, execute_values

from app.database import database_transaction, init_db
from app.ScriptingFiles.FullDataScript.ingestion import _slug_from_name, http_session
from app.ScriptingFiles.FullDataScript.ingestion_tracking import tracked_ingestion


CAPSPACE_BASE_URL = "https://cap-space.com"
CAPWAGES_BASE_URL = "https://capwages.com"
CAPSPACE_SOURCE = "capspace"
CAPWAGES_SOURCE = "capwages"
STATUS_FAILED = "failed"
STATUS_NO_CONTRACTS = "no_contracts"
STATUS_NO_MATCHING_CONTRACTS = "no_matching_contracts"
STATUS_NO_NHL_ID = "no_nhl_id"
STATUS_NOT_FOUND = "not_found"
STATUS_PARSE_FAILED = "parse_failed"
STATUS_SUCCEEDED = "succeeded"
FAILURE_STATUSES = frozenset({STATUS_FAILED, STATUS_PARSE_FAILED})
RETRYABLE_HTTP_STATUSES = frozenset({429, 500, 502, 503, 504})
CAPWAGES_SLUG_SUFFIXES = ("", "-1", "-2", "-3")
AUXILIARY_TABLE_PREFIXES = (
    "buyout years",
    "termination fees",
    "cap recapture",
)
NO_CONTRACT_MARKERS = re.compile(
    r"Contract History|No recorded contracts|Total Value\s*:", re.I
)
DEFAULT_FIRST_SEASON = 2008
DEFAULT_LAST_SEASON = 2025
MAX_WORKERS = 8
DEFAULT_BATCH_SIZE = 100
MAX_BATCH_SIZE = 1000
STAT_SEASONS_CTE = """stat_seasons AS (
    SELECT DISTINCT player_id,season_start_year
      FROM skater_season_stats
     WHERE game_type=2
       AND COALESCE(games_played,0)>0
       AND season_start_year BETWEEN %s AND %s
    UNION
    SELECT DISTINCT player_id,season_start_year
      FROM goalie_season_stats
     WHERE game_type=2
       AND COALESCE(games_played,0)>0
       AND season_start_year BETWEEN %s AND %s
)"""
MISSING_CONTRACT_PREDICATE = """NOT EXISTS (
    SELECT 1
      FROM contracts c
      JOIN contract_seasons cs ON cs.contract_id=c.id
     WHERE c.player_id=s.player_id
       AND cs.season_start_year=s.season_start_year
)"""


class CapSpaceError(RuntimeError):
    """A source or parser failure that is safe to report per player."""


class CapSpaceParseError(CapSpaceError):
    """The page was reachable but no trustworthy contract structure was found."""


@dataclass(frozen=True)
class ContractSeason:
    season_start_year: int
    cap_hit_cents: int
    base_salary_cents: int | None = None
    signing_bonus_cents: int | None = None
    performance_bonus_cents: int | None = None
    minors_salary_cents: int | None = None
    clause: str | None = None
    owning_team: str | None = None
    is_slide: bool = False
    source_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class ParsedContract:
    contract_type: str | None
    is_entry_level: bool
    total_value_cents: int | None
    term_years: int
    signed_on: date | None
    signing_team: str | None
    expiry_status: str | None
    seasons: tuple[ContractSeason, ...]
    external_id: str | None = None
    source_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class Candidate:
    player_id: int
    first_name: str
    last_name: str
    nhl_id: str | None
    missing_seasons: tuple[int, ...]


@dataclass(frozen=True)
class ProfileResult:
    candidate: Candidate
    url: str
    status: str
    contracts: tuple[ParsedContract, ...] = ()
    error: str | None = None
    html: str | None = None
    source_code: str = CAPSPACE_SOURCE
    fallback_attempted: bool = False
    primary_status: str | None = None
    fallback_status: str | None = None

    @property
    def target_seasons_covered(self) -> frozenset[int]:
        targets = set(self.candidate.missing_seasons)
        return frozenset(
            season.season_start_year
            for contract in self.contracts
            for season in contract.seasons
            if season.season_start_year in targets
        )

    @property
    def covers_target(self) -> bool:
        return bool(self.target_seasons_covered)


def money_to_cents(value: Any) -> int | None:
    """Convert a dollar string to cents without turning malformed input into zero."""
    if value is None or str(value).strip() in {"", "-", "—", "–", "N/A", "NA"}:
        return None
    text = str(value).strip().replace("$", "").replace(",", "").replace(" ", "")
    try:
        amount = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise CapSpaceParseError(f"malformed monetary value: {value!r}") from exc
    if not amount.is_finite() or amount < 0:
        raise CapSpaceParseError(f"invalid monetary value: {value!r}")
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def season_start_year(value: Any) -> int:
    text = " ".join(str(value or "").replace("–", "-").replace("—", "-").split())
    match = re.fullmatch(r"(\d{4})\s*-\s*(?:\d{2}|\d{4})", text)
    if not match:
        raise CapSpaceParseError(f"malformed season: {value!r}")
    year = int(match.group(1))
    if year < 1900 or year > 2200:
        raise CapSpaceParseError(f"unreasonable season: {value!r}")
    return year


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


def _date_value(value: Any) -> date | None:
    text = _clean_text(value)
    if not text:
        return None
    for pattern in (r"(\d{4})-(\d{1,2})-(\d{1,2})", r"(\d{1,2})/(\d{1,2})/(\d{4})"):
        match = re.search(pattern, text)
        if match:
            parts = [int(part) for part in match.groups()]
            if pattern.startswith("(\\d{1,2}"):
                parts = [parts[2], parts[0], parts[1]]
            try:
                return date(*parts)
            except ValueError as exc:
                raise CapSpaceParseError(f"malformed signing date: {value!r}") from exc
    month_match = re.fullmatch(
        r"([A-Za-z]{3,9})\.?\s+(\d{1,2}),\s*(\d{4})", text
    )
    if month_match:
        month_names = {
            name: index
            for index, names in enumerate(
                (
                    (),
                    ("jan", "january"), ("feb", "february"),
                    ("mar", "march"), ("apr", "april"), ("may",),
                    ("jun", "june"), ("jul", "july"),
                    ("aug", "august"), ("sep", "sept", "september"),
                    ("oct", "october"), ("nov", "november"),
                    ("dec", "december"),
                )
            )
            for name in names
        }
        month = month_names.get(month_match.group(1).lower())
        if month:
            try:
                return date(int(month_match.group(3)), month, int(month_match.group(2)))
            except ValueError as exc:
                raise CapSpaceParseError(f"malformed signing date: {value!r}") from exc
    raise CapSpaceParseError(f"malformed signing date: {value!r}")


def _expiry(value: Any) -> str | None:
    text = _clean_text(value).upper()
    if "RFA" in text:
        return "RFA"
    if "UFA" in text:
        return "UFA"
    return None


def _contract_type(value: Any) -> str | None:
    text = _clean_text(value)
    return text[:32] or None


class _Node:
    def __init__(self, tag: str = "root", attrs: dict[str, str] | None = None, parent: _Node | None = None):
        self.tag = tag
        self.attrs = attrs or {}
        self.parent = parent
        self.children: list[_Node | str] = []

    def text(self) -> str:
        return _clean_text(" ".join(child if isinstance(child, str) else child.text() for child in self.children))


class _TreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node()
        self.current = self.root

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Node(tag.lower(), {key.lower(): value or "" for key, value in attrs}, self.current)
        self.current.children.append(node)
        if tag.lower() not in {"meta", "link", "img", "input", "br", "hr"}:
            self.current = node

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        node = self.current
        while node is not self.root:
            if node.tag == tag.lower():
                self.current = node.parent or self.root
                return
            node = node.parent or self.root

    def handle_data(self, data: str) -> None:
        if data:
            self.current.children.append(data)


@dataclass(frozen=True)
class _SourceDocument:
    html: str
    root: _Node
    next_data: tuple[dict[str, Any], ...]

    @classmethod
    def parse(cls, html: str) -> _SourceDocument:
        parser = _TreeParser()
        parser.feed(html)
        payloads: list[dict[str, Any]] = []
        for node in _descendants(parser.root, "script"):
            if node.attrs.get("id") != "__NEXT_DATA__":
                continue
            try:
                payload = json.loads(node.text())
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(payload, dict):
                payloads.append(payload)
        return cls(html=html, root=parser.root, next_data=tuple(payloads))


def _descendants(node: _Node, tag: str | None = None) -> list[_Node]:
    found: list[_Node] = []
    for child in node.children:
        if isinstance(child, _Node):
            if tag is None or child.tag == tag:
                found.append(child)
            found.extend(_descendants(child, tag))
    return found


def _classes(node: _Node) -> set[str]:
    return set(node.attrs.get("class", "").split())


def _page_player(payload: dict[str, Any]) -> dict[str, Any]:
    page = payload.get("props", {}).get("pageProps", {})
    player = page.get("player") or page.get("person") or {}
    return player if isinstance(player, dict) else {}


def _embedded_nhl_id(document: _SourceDocument) -> str | None:
    for payload in document.next_data:
        player = _page_player(payload)
        if player.get("nhlId") is not None:
            return str(player["nhlId"])
    return None


def _is_entry_level(value: Any) -> bool:
    contract_type = _clean_text(value).upper()
    return "ENTRY" in contract_type or "ELC" in contract_type


def _season_from_mapping(row: dict[str, Any]) -> ContractSeason:
    normalized = {re.sub(r"[^a-z]", "", str(key).lower()): value for key, value in row.items()}
    season = season_start_year(normalized.get("season"))
    cap_hit = money_to_cents(normalized.get("caphit", normalized.get("caphitcents")))
    if cap_hit is None:
        raise CapSpaceParseError(f"missing cap hit for season {row.get('season')!r}")
    raw_nhl = normalized.get("nhlsalary", normalized.get("basesalary"))
    is_slide = "slide" in _clean_text(raw_nhl).lower()
    return ContractSeason(
        season_start_year=season,
        cap_hit_cents=cap_hit,
        base_salary_cents=None if is_slide else money_to_cents(raw_nhl),
        signing_bonus_cents=money_to_cents(
            normalized.get("signingbonus", normalized.get("signingbonuses"))
        ),
        performance_bonus_cents=money_to_cents(
            normalized.get(
                "performancebonus",
                normalized.get(
                    "performancebonuses",
                    normalized.get("perfbonus", normalized.get("perfbonuses")),
                ),
            )
        ),
        minors_salary_cents=money_to_cents(normalized.get("minor salary", normalized.get("minorssalary"))),
        clause=_clean_text(normalized.get("clause")) or None,
        owning_team=_clean_text(normalized.get("owningteam", normalized.get("team"))) or None,
        is_slide=is_slide,
        source_payload=dict(row),
    )


def _contracts_from_json(payload: dict[str, Any]) -> list[ParsedContract]:
    page = payload.get("props", {}).get("pageProps", {})
    person = page.get("person") or page.get("player") or {}
    raw_contracts = person.get("contracts") or page.get("contracts") or []
    parsed: list[ParsedContract] = []
    for raw in raw_contracts:
        if not isinstance(raw, dict):
            continue
        details = raw.get("details") or raw.get("seasons") or []
        seasons = []
        for row in details:
            if not isinstance(row, dict):
                continue
            try:
                seasons.append(_season_from_mapping(row))
            except CapSpaceParseError:
                continue
        if not seasons:
            continue
        try:
            raw_start = min(row.season_start_year for row in seasons)
            raw_end = max(row.season_start_year for row in seasons)
            term = int(raw.get("term") or raw.get("termYears") or raw.get("seasonsCount") or len(seasons))
            if term <= 0 or raw_end < raw_start or len({row.season_start_year for row in seasons}) != len(seasons):
                continue
            parsed.append(
                ParsedContract(
                    contract_type=_contract_type(raw.get("type") or raw.get("contractType")),
                    is_entry_level=_is_entry_level(
                        raw.get("type") or raw.get("contractType")
                    ),
                    total_value_cents=money_to_cents(raw.get("value") or raw.get("totalValue")),
                    term_years=term,
                    signed_on=_date_value(raw.get("signingDate") or raw.get("signed_on")),
                    signing_team=_clean_text(raw.get("signingTeam") or raw.get("team")) or None,
                    expiry_status=_expiry(raw.get("expiryStatus") or raw.get("expiry")),
                    seasons=tuple(seasons),
                    external_id=_clean_text(raw.get("id") or raw.get("contractId")) or None,
                    source_payload=raw,
                )
            )
        except (CapSpaceParseError, TypeError, ValueError):
            continue
    return parsed


def _table_rows(block: _Node) -> list[dict[str, str]]:
    tables = _descendants(block, "table")
    for table in tables:
        rows = _descendants(table, "tr")
        for header_index, row in enumerate(rows):
            header_cells = [
                node for node in row.children
                if isinstance(node, _Node) and node.tag in {"th", "td"}
            ]
            if not header_cells:
                continue
            headers = [re.sub(r"[^a-z]", "", cell.text().lower()) for cell in header_cells]
            # CapSpace currently renders the season-table header as <td>, and
            # places contract metadata in a separate table before it.
            if "season" not in headers or "caphit" not in headers:
                continue
            parsed: list[dict[str, str]] = []
            for data_row in rows[header_index + 1:]:
                cells = [
                    node for node in data_row.children
                    if isinstance(node, _Node) and node.tag in {"th", "td"}
                ]
                if not cells:
                    continue
                values = [_clean_text(cell.text()) for cell in cells]
                first_value = values[0].lower() if values else ""
                if first_value.startswith(AUXILIARY_TABLE_PREFIXES):
                    break
                # A contract table can contain lockout rows, auxiliary
                # sections, or a repeated header for buyout data. Keep only
                # rows that have a real season and monetary cap hit.
                try:
                    season_start_year(values[0])
                    money_to_cents(values[1])
                except (IndexError, CapSpaceParseError):
                    continue
                if len(values) < len(headers):
                    values.extend([""] * (len(headers) - len(values)))
                parsed.append(dict(zip(headers, values)))
            if parsed:
                return parsed
    return []


def _document_contracts(document: _SourceDocument) -> list[ParsedContract]:
    for payload in document.next_data:
        try:
            json_contracts = _contracts_from_json(payload)
        except (TypeError, CapSpaceError):
            json_contracts = []
        if json_contracts:
            return json_contracts

    candidates = []
    for node in _descendants(document.root):
        text = node.text()
        classes = _classes(node)
        if (node.tag == "article" or "contract" in classes or "contract-block" in classes) and "Total Value" in text and _descendants(node, "table"):
            candidates.append(node)
    blocks = [node for node in candidates if not any(parent in candidates for parent in _parents(node))]
    result: list[ParsedContract] = []
    for block in blocks:
        text = block.text()
        rows = _table_rows(block)
        seasons = []
        for row in rows:
            try:
                seasons.append(_season_from_mapping(row))
            except CapSpaceParseError:
                continue
        if not seasons:
            continue
        value_match = re.search(r"Total Value\s*:\s*(\$?[0-9][0-9,]*(?:\.[0-9]+)?)", text, re.I)
        term_match = re.search(r"Seasons?\s*:\s*(\d+)", text, re.I)
        date_match = re.search(r"Signing Date\s*:\s*(\d{4}-\d{1,2}-\d{1,2})", text, re.I)
        expiry_match = re.search(r"Expiration Status\s*:\s*(RFA|UFA)", text, re.I)
        team_match = re.search(r"Signing Team\s*:\s*(.+?)(?=\s*\|?\s*Season\s+|\s*Cap Hit\b|$)", text, re.I)
        headings = [_clean_text(node.text()) for node in _descendants(block) if node.tag in {"h2", "h3", "h4"}]
        contract_type = next((heading for heading in headings if "contract" in heading.lower()), None)
        parsed_type = _contract_type(contract_type)
        signed_on = None
        if date_match:
            try:
                signed_on = _date_value(date_match.group(1).strip())
            except CapSpaceParseError:
                pass
        total_value = None
        if value_match:
            try:
                total_value = money_to_cents(value_match.group(1).strip())
            except CapSpaceParseError:
                pass
        result.append(
            ParsedContract(
                contract_type=parsed_type,
                is_entry_level=_is_entry_level(parsed_type),
                total_value_cents=total_value,
                term_years=int(term_match.group(1)) if term_match else len(seasons),
                signed_on=signed_on,
                signing_team=_clean_text(team_match.group(1)) or None if team_match else None,
                expiry_status=_expiry(expiry_match.group(1)) if expiry_match else None,
                seasons=tuple(seasons),
                external_id=block.attrs.get("data-contract-id") or block.attrs.get("data-external-id") or None,
                source_payload={"text": text, "rows": rows},
            )
        )
    return result


def _parents(node: _Node) -> list[_Node]:
    result = []
    parent = node.parent
    while parent:
        result.append(parent)
        parent = parent.parent
    return result


def _parse_contract_document(
    document: _SourceDocument,
    *,
    expected_nhl_id: str | None = None,
    require_nhl_id: bool = False,
) -> tuple[ParsedContract, ...]:
    if expected_nhl_id:
        returned_id = _embedded_nhl_id(document)
        if require_nhl_id and returned_id is None:
            raise CapSpaceParseError("source page does not expose an NHL ID")
        if returned_id is not None and returned_id != str(expected_nhl_id):
            raise CapSpaceParseError("source page does not match requested NHL ID")
    contracts = _document_contracts(document)
    if not contracts:
        if NO_CONTRACT_MARKERS.search(document.html):
            return ()
        raise CapSpaceParseError("CapSpace contract markup was not recognised")
    for contract in contracts:
        if contract.term_years <= 0 or len({row.season_start_year for row in contract.seasons}) != len(contract.seasons):
            raise CapSpaceParseError("duplicate or invalid contract seasons")
    return tuple(contracts)


def parse_capspace_page(
    html: str,
    *,
    expected_nhl_id: str | None = None,
    require_nhl_id: bool = False,
) -> tuple[ParsedContract, ...]:
    """Parse a CapSpace/CapWages page and optionally require NHL-ID identity."""
    if not isinstance(html, str) or not html.strip():
        raise CapSpaceParseError("empty CapSpace response")
    return _parse_contract_document(
        _SourceDocument.parse(html),
        expected_nhl_id=expected_nhl_id,
        require_nhl_id=require_nhl_id,
    )


def normalize_contracts(
    contracts: Iterable[ParsedContract],
    nhl_id: str,
    source_code: str = CAPSPACE_SOURCE,
) -> tuple[ParsedContract, ...]:
    normalized = []
    for index, contract in enumerate(contracts):
        first = min(row.season_start_year for row in contract.seasons)
        last = max(row.season_start_year for row in contract.seasons)
        external_id = contract.external_id or f"{source_code}:{nhl_id}:{first}:{last}:{index}"
        normalized.append(replace(contract, external_id=external_id))
    return tuple(normalized)


def select_candidates(
    cursor,
    *,
    first_season: int = DEFAULT_FIRST_SEASON,
    last_season: int = DEFAULT_LAST_SEASON,
    player_id: int | None = None,
    nhl_id: str | None = None,
    limit: int | None = None,
    force: bool = False,
) -> list[Candidate]:
    filters = []
    params: list[Any] = [
        first_season,
        last_season,
        first_season,
        last_season,
    ]
    if player_id is not None:
        filters.append("p.id = %s")
        params.append(player_id)
    if nhl_id is not None:
        filters.append("nhl.external_id = %s")
        params.append(str(nhl_id))
    if not force:
        filters.append(MISSING_CONTRACT_PREDICATE)
    where_clause = " AND ".join(filters) if filters else "TRUE"
    limit_sql = " LIMIT %s" if limit else ""
    if limit:
        params.append(limit)
    cursor.execute(
        f"""WITH {STAT_SEASONS_CTE}
             SELECT s.player_id, p.first_name, p.last_name, nhl.external_id,
                    array_agg(s.season_start_year ORDER BY s.season_start_year)
               FROM stat_seasons s
               JOIN players p ON p.id=s.player_id
               LEFT JOIN data_sources nhl_src ON nhl_src.code='nhl'
               LEFT JOIN player_external_ids nhl
                 ON nhl.player_id=p.id AND nhl.source_id=nhl_src.id
              WHERE {where_clause}
              GROUP BY s.player_id,p.first_name,p.last_name,nhl.external_id
              ORDER BY s.player_id{limit_sql}""",
        params,
    )
    return [
        Candidate(int(row[0]), row[1], row[2], str(row[3]) if row[3] else None, tuple(row[4]))
        for row in cursor.fetchall()
    ]


def _team_lookup(cursor) -> dict[str, int]:
    cursor.execute("SELECT id,abbreviation,name FROM teams")
    lookup: dict[str, int] = {}
    for team_id, abbreviation, name in cursor.fetchall():
        for value in (abbreviation, name):
            key = _clean_text(value).casefold()
            if key:
                lookup[key] = int(team_id)
    return lookup


@dataclass(frozen=True)
class _PersistenceContext:
    season_caps: dict[int, int | None]
    team_lookup: dict[str, int]


def _load_persistence_context(
    cursor,
    first_season: int,
    last_season: int,
) -> _PersistenceContext:
    cursor.execute(
        """SELECT start_year,salary_cap_cents
             FROM seasons
            WHERE start_year BETWEEN %s AND %s""",
        (first_season - 10, last_season),
    )
    return _PersistenceContext(
        season_caps={int(year): cap for year, cap in cursor.fetchall()},
        team_lookup=_team_lookup(cursor),
    )


def _player_stint_teams(cursor, player_id: int) -> dict[int, tuple[int, ...]]:
    cursor.execute(
        """SELECT DISTINCT season_start_year,team_id
             FROM player_team_stints
            WHERE player_id=%s""",
        (player_id,),
    )
    teams_by_season: dict[int, list[int]] = {}
    for season, team_id in cursor.fetchall():
        teams_by_season.setdefault(int(season), []).append(int(team_id))
    return {
        season: tuple(team_ids)
        for season, team_ids in teams_by_season.items()
    }


def _resolve_team_id(
    team_lookup: dict[str, int],
    stint_teams: dict[int, tuple[int, ...]],
    season: int,
    explicit: str | None,
) -> int | None:
    explicit_id = team_lookup.get(_clean_text(explicit).casefold())
    if explicit_id is not None:
        return explicit_id
    teams = stint_teams.get(season, ())
    return teams[0] if len(teams) == 1 else None


def _compatible(existing: tuple[Any, ...], incoming: ParsedContract, team_id: int | None) -> bool:
    _, existing_team, _, _, _, _, _, _, total_value, _, _ = existing
    if existing_team and team_id and existing_team != team_id:
        return False
    if (
        total_value is not None
        and incoming.total_value_cents is not None
        and total_value != incoming.total_value_cents
    ):
        return False
    return True


def _contract_row(cursor, contract_id: int) -> tuple[Any, ...]:
    cursor.execute(
        """SELECT id,signing_team_id,source_id,external_id,start_season,
                  end_season,term_years,contract_type,total_value_cents,
                  average_value_cents,is_entry_level
             FROM contracts
            WHERE id=%s""",
        (contract_id,),
    )
    row = cursor.fetchone()
    if row is None:
        raise CapSpaceError(f"contract {contract_id} disappeared during reconciliation")
    return row


@dataclass(frozen=True)
class _ResolvedContract:
    contract_id: int | None
    existing_seasons: dict[int, tuple[int, int]]


def _average_value(contract: ParsedContract) -> int | None:
    if contract.total_value_cents is None:
        return None
    return contract.total_value_cents // contract.term_years


def _record_conflict(summary: Counter[str]) -> None:
    summary["reconciliation_conflicts"] += 1
    summary["records_skipped"] += 1


def _matching_contract_id(
    cursor,
    *,
    player_id: int,
    source_id: int,
    contract: ParsedContract,
    signing_team_id: int | None,
    start: int,
    end: int,
) -> tuple[int | None, bool]:
    cursor.execute(
        "SELECT id FROM contracts WHERE source_id=%s AND external_id=%s",
        (source_id, contract.external_id),
    )
    source_match = cursor.fetchone()
    if source_match:
        return int(source_match[0]), False

    cursor.execute(
        """SELECT id
             FROM contracts
            WHERE player_id=%s AND start_season=%s AND end_season=%s
              AND term_years=%s""",
        (player_id, start, end, contract.term_years),
    )
    matches = [int(row[0]) for row in cursor.fetchall()]
    compatible = [
        contract_id
        for contract_id in matches
        if _compatible(_contract_row(cursor, contract_id), contract, signing_team_id)
    ]
    conflict = len(matches) > 1 or bool(matches and not compatible)
    return (compatible[0] if compatible else None), conflict


def _existing_contract_seasons(
    cursor,
    contract_id: int,
    seasons: Iterable[ContractSeason],
) -> dict[int, tuple[int, int]]:
    cursor.execute(
        """SELECT id,season_start_year,cap_hit_cents
             FROM contract_seasons
            WHERE contract_id=%s AND season_start_year = ANY(%s)""",
        (contract_id, [row.season_start_year for row in seasons]),
    )
    return {
        int(season): (int(season_id), cap_hit)
        for season_id, season, cap_hit in cursor.fetchall()
    }


def _resolve_contract(
    cursor,
    *,
    player_id: int,
    source_id: int,
    contract: ParsedContract,
    signing_team_id: int | None,
    start: int,
    end: int,
    seasons_to_write: tuple[ContractSeason, ...],
    summary: Counter[str],
    preview: bool,
) -> _ResolvedContract | None:
    contract_id, conflict = _matching_contract_id(
        cursor,
        player_id=player_id,
        source_id=source_id,
        contract=contract,
        signing_team_id=signing_team_id,
        start=start,
        end=end,
    )
    if conflict:
        _record_conflict(summary)
        return None

    existing_seasons: dict[int, tuple[int, int]] = {}
    if contract_id is not None:
        existing = _contract_row(cursor, contract_id)
        if not _compatible(existing, contract, signing_team_id):
            _record_conflict(summary)
            return None
        existing_seasons = _existing_contract_seasons(
            cursor, contract_id, seasons_to_write
        )
        if any(
            existing_seasons.get(row.season_start_year, (0, None))[1]
            not in (None, row.cap_hit_cents)
            for row in seasons_to_write
        ):
            _record_conflict(summary)
            return None
        summary["contracts_matched"] += 1
        if not preview:
            cursor.execute(
                """UPDATE contracts
                      SET signed_on=COALESCE(signed_on,%s),
                          signing_team_id=COALESCE(signing_team_id,%s),
                          contract_type=COALESCE(contract_type,%s),
                          expiry_status=COALESCE(expiry_status,%s),
                          total_value_cents=COALESCE(total_value_cents,%s),
                          average_value_cents=COALESCE(average_value_cents,%s),
                          source_payload=CASE
                              WHEN source_payload='{}'::jsonb THEN %s
                              ELSE source_payload END,
                          updated_at=CURRENT_TIMESTAMP
                    WHERE id=%s""",
                (
                    contract.signed_on,
                    signing_team_id,
                    contract.contract_type,
                    contract.expiry_status,
                    contract.total_value_cents,
                    _average_value(contract),
                    Json(contract.source_payload or {}),
                    contract_id,
                ),
            )
        return _ResolvedContract(contract_id, existing_seasons)

    summary["contracts_created"] += 1
    if not preview:
        cursor.execute(
            """INSERT INTO contracts
                   (player_id,signing_team_id,source_id,external_id,signed_on,
                    start_season,end_season,term_years,contract_type,
                    expiry_status,total_value_cents,average_value_cents,
                    is_entry_level,source_payload)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id""",
            (
                player_id,
                signing_team_id,
                source_id,
                contract.external_id,
                contract.signed_on,
                start,
                end,
                contract.term_years,
                contract.contract_type,
                contract.expiry_status,
                contract.total_value_cents,
                _average_value(contract),
                contract.is_entry_level,
                Json(contract.source_payload or {}),
            ),
        )
        contract_id = int(cursor.fetchone()[0])
    return _ResolvedContract(contract_id, existing_seasons)


def _persist_contracts(
    cursor,
    player_id: int,
    nhl_id: str,
    contracts: Iterable[ParsedContract],
    first_season: int,
    last_season: int,
    source_id: int,
    summary: Counter[str],
    *,
    target_seasons: Iterable[int] | None = None,
    preview: bool = False,
    source_code: str = CAPSPACE_SOURCE,
    context: _PersistenceContext | None = None,
) -> None:
    persistence = context or _load_persistence_context(
        cursor, first_season, last_season
    )
    season_caps = persistence.season_caps
    available = set(season_caps)
    team_lookup = persistence.team_lookup
    stint_teams = {} if preview else _player_stint_teams(cursor, player_id)
    targets = set(target_seasons) if target_seasons is not None else None
    pending_seasons: list[tuple[Any, ...]] = []
    for contract in normalize_contracts(contracts, nhl_id, source_code):
        seasons = tuple(
            row
            for row in contract.seasons
            if row.season_start_year in available
            and first_season - 10 <= row.season_start_year <= last_season
        )
        if not seasons:
            summary["records_skipped"] += 1
            continue
        seasons_to_write = tuple(
            row
            for row in seasons
            if targets is None or row.season_start_year in targets
        )
        if not seasons_to_write:
            continue
        start = min(row.season_start_year for row in seasons)
        end = max(row.season_start_year for row in seasons)
        signing_team_id = team_lookup.get(
            _clean_text(contract.signing_team).casefold()
        )
        resolved = _resolve_contract(
            cursor,
            player_id=player_id,
            source_id=source_id,
            contract=contract,
            signing_team_id=signing_team_id,
            start=start,
            end=end,
            seasons_to_write=seasons_to_write,
            summary=summary,
            preview=preview,
        )
        if resolved is None:
            continue
        contract_id = resolved.contract_id
        existing_seasons = resolved.existing_seasons
        if preview:
            summary["contract_seasons_updated"] += sum(
                row.season_start_year in existing_seasons
                for row in seasons_to_write
            )
            summary["contract_seasons_created"] += sum(
                row.season_start_year not in existing_seasons
                for row in seasons_to_write
            )
            continue
        for row in seasons_to_write:
            owning_team_id = _resolve_team_id(
                team_lookup,
                stint_teams,
                row.season_start_year,
                row.owning_team,
            )
            base = row.base_salary_cents
            total_cash = base + row.signing_bonus_cents if base is not None and row.signing_bonus_cents is not None else base
            cap = season_caps[row.season_start_year]
            cap_pct = Decimal(row.cap_hit_cents) / Decimal(cap) if cap else None
            existing_season = existing_seasons.get(row.season_start_year)
            if existing_season:
                existing_season_id, existing_cap_hit = existing_season
                if existing_cap_hit != row.cap_hit_cents:
                    summary["reconciliation_conflicts"] += 1
                    continue
                cursor.execute("""UPDATE contract_seasons SET owning_team_id=COALESCE(owning_team_id,%s), base_salary_cents=COALESCE(base_salary_cents,%s), signing_bonus_cents=COALESCE(signing_bonus_cents,%s), performance_bonus_cents=COALESCE(performance_bonus_cents,%s), total_cash_cents=COALESCE(total_cash_cents,%s), cap_percentage=COALESCE(cap_percentage,%s), clauses=CASE WHEN clauses='{}'::jsonb THEN %s ELSE clauses END, is_slide=is_slide OR %s, updated_at=CURRENT_TIMESTAMP WHERE id=%s""", (owning_team_id, base, row.signing_bonus_cents, row.performance_bonus_cents, total_cash, cap_pct, Json({"clause": row.clause, "minors_salary_cents": row.minors_salary_cents, "source": source_code}), row.is_slide, existing_season_id))
                summary["contract_seasons_updated"] += 1
            else:
                pending_seasons.append((contract_id, row.season_start_year, owning_team_id, base, row.signing_bonus_cents, row.performance_bonus_cents, total_cash, row.cap_hit_cents, cap_pct, row.is_slide, Json({"clause": row.clause, "minors_salary_cents": row.minors_salary_cents, "source": source_code})))
    if pending_seasons:
        execute_values(cursor, """INSERT INTO contract_seasons (contract_id,season_start_year,owning_team_id,base_salary_cents,signing_bonus_cents,performance_bonus_cents,total_cash_cents,cap_hit_cents,cap_percentage,is_slide,clauses)
            VALUES %s""", pending_seasons, page_size=500)
        summary["contract_seasons_created"] += len(pending_seasons)


def _source_record_values(source_id: int, source_code: str, candidate: Candidate, payload: dict[str, Any]) -> tuple[Any, ...]:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    safe_payload = json.loads(encoded)
    return (source_id, f"{source_code}_player_profile", candidate.nhl_id or str(candidate.player_id), hashlib.sha256(encoded.encode()).hexdigest(), Json(safe_payload))


def _source_records_bulk(cursor, source_id: int, source_code: str, records: Iterable[tuple[Candidate, dict[str, Any]]]) -> None:
    values = [_source_record_values(source_id, source_code, candidate, payload) for candidate, payload in records]
    if not values:
        return
    execute_values(cursor, """INSERT INTO source_records (source_id,entity_type,external_key,payload_hash,payload)
        VALUES %s ON CONFLICT (source_id,entity_type,external_key,payload_hash) DO NOTHING""", values, page_size=500)


def _fetch_profile(session: requests.Session, candidate: Candidate, *, max_attempts: int = 4) -> ProfileResult:
    if not candidate.nhl_id:
        return ProfileResult(candidate, "", STATUS_NO_NHL_ID)
    url = f"{CAPSPACE_BASE_URL}/person/nhl:{candidate.nhl_id}"
    for attempt in range(max_attempts):
        try:
            response = session.get(url, timeout=30)
        except requests.RequestException as exc:
            if attempt + 1 == max_attempts:
                return ProfileResult(
                    candidate,
                    url,
                    STATUS_FAILED,
                    error="timeout" if isinstance(exc, requests.Timeout) else str(exc),
                )
            time.sleep(min(2**attempt, 8))
            continue
        if response.status_code == 404:
            return ProfileResult(candidate, url, STATUS_NOT_FOUND)
        if response.status_code == 200:
            returned_url = getattr(response, "url", "")
            if (
                isinstance(returned_url, str)
                and returned_url
                and f"/person/nhl:{candidate.nhl_id}" not in returned_url
            ):
                return ProfileResult(
                    candidate,
                    url,
                    STATUS_PARSE_FAILED,
                    error="CapSpace redirected to a different player identity",
                    html=response.text,
                )
            try:
                contracts = parse_capspace_page(
                    response.text, expected_nhl_id=candidate.nhl_id
                )
            except CapSpaceError as exc:
                return ProfileResult(
                    candidate,
                    url,
                    STATUS_PARSE_FAILED,
                    error=str(exc),
                    html=response.text,
                )
            status = STATUS_NO_CONTRACTS if not contracts else STATUS_SUCCEEDED
            return ProfileResult(candidate, url, status, contracts, html=response.text)
        retryable = response.status_code in RETRYABLE_HTTP_STATUSES
        if not retryable or attempt + 1 == max_attempts:
            return ProfileResult(
                candidate,
                url,
                STATUS_FAILED,
                error=f"HTTP {response.status_code}",
            )
        retry_after = response.headers.get("Retry-After")
        try:
            delay = min(float(retry_after), 30) if retry_after else min(2**attempt, 8)
        except ValueError:
            delay = min(2**attempt, 8)
        time.sleep(delay)
    return ProfileResult(candidate, url, STATUS_FAILED, error="retry exhaustion")


def _target_seasons_covered(result: ProfileResult) -> set[int]:
    """Backward-compatible helper for callers that need a mutable set."""
    return set(result.target_seasons_covered)


def _capwages_document_matches(
    document: _SourceDocument,
    candidate: Candidate,
    url: str,
) -> bool:
    """Validate legacy profiles that predate CapWages' NHL-ID field.

    Newer pages are keyed by NHL ID. Older pages must instead agree on the
    canonical name and slug and expose an NHL stats season that overlaps this
    player's missing-season target. This avoids accepting a same-name profile
    based on its URL alone.
    """
    for payload in document.next_data:
        player = _page_player(payload)
        if player.get("nhlId") is not None:
            return str(player["nhlId"]) == str(candidate.nhl_id)
        expected_slug = _slug_from_name(
            f"{candidate.first_name} {candidate.last_name}"
        )
        page_slug = _clean_text(player.get("slug")).lower()
        page_name_slug = _slug_from_name(_clean_text(player.get("name")))
        url_slug = url.rstrip("/").rsplit("/", 1)[-1].lower()
        if (
            not expected_slug
            or page_name_slug != expected_slug
            or page_slug != url_slug
            or not (url_slug == expected_slug or url_slug.startswith(f"{expected_slug}-"))
        ):
            return False
        stats_seasons = set()
        for row in player.get("stats") or []:
            if not isinstance(row, dict) or _clean_text(row.get("league")).upper() != "NHL":
                continue
            match = re.match(
                r"(\d{4})",
                _clean_text(row.get("season") or row.get("platformSeason")),
            )
            games = str(row.get("gp") or "0").strip()
            if match and games.isdigit() and int(games) > 0:
                stats_seasons.add(int(match.group(1)))
        return bool(stats_seasons & set(candidate.missing_seasons))
    return False


def _capwages_identity_matches(
    html: str,
    candidate: Candidate,
    url: str,
) -> bool:
    return _capwages_document_matches(_SourceDocument.parse(html), candidate, url)


def _fetch_capwages_profile(
    session: requests.Session,
    candidate: Candidate,
) -> ProfileResult:
    """Try CapWages slugs with strong identity checks and bounded requests."""
    if not candidate.nhl_id:
        return ProfileResult(
            candidate, "", STATUS_NO_NHL_ID, source_code=CAPWAGES_SOURCE
        )
    slug = _slug_from_name(f"{candidate.first_name} {candidate.last_name}")
    if not slug:
        return ProfileResult(
            candidate,
            "",
            STATUS_NOT_FOUND,
            error="player name cannot form a CapWages slug",
            source_code=CAPWAGES_SOURCE,
        )
    last_result: ProfileResult | None = None
    for suffix in CAPWAGES_SLUG_SUFFIXES:
        url = f"{CAPWAGES_BASE_URL}/players/{slug}{suffix}"
        try:
            response = session.get(url, timeout=30)
        except requests.RequestException as exc:
            last_result = ProfileResult(
                candidate,
                url,
                STATUS_FAILED,
                error="timeout" if isinstance(exc, requests.Timeout) else str(exc),
                source_code=CAPWAGES_SOURCE,
            )
            continue
        if response.status_code == 404 and not suffix:
            # Numbered slugs only exist to disambiguate a base slug already
            # owned by a same-name player. Avoid three guaranteed misses for
            # every historical candidate absent from CapWages.
            return ProfileResult(
                candidate,
                url,
                STATUS_NOT_FOUND,
                source_code=CAPWAGES_SOURCE,
            )
        if response.status_code == 404:
            continue
        if response.status_code != 200:
            # A rate-limit or source outage applies to the host, not just this
            # guessed slug. Stop rather than multiplying requests.
            return ProfileResult(
                candidate,
                url,
                STATUS_FAILED,
                error=f"HTTP {response.status_code}",
                source_code=CAPWAGES_SOURCE,
            )
        document = _SourceDocument.parse(response.text)
        if not _capwages_document_matches(document, candidate, url):
            last_result = ProfileResult(
                candidate,
                url,
                STATUS_PARSE_FAILED,
                error="CapWages profile identity could not be validated",
                html=response.text,
                source_code=CAPWAGES_SOURCE,
            )
            continue
        try:
            contracts = _parse_contract_document(
                document,
                expected_nhl_id=candidate.nhl_id,
            )
        except CapSpaceError as exc:
            last_result = ProfileResult(
                candidate,
                url,
                STATUS_PARSE_FAILED,
                error=str(exc),
                html=response.text,
                source_code=CAPWAGES_SOURCE,
            )
            return last_result
        result = ProfileResult(
            candidate,
            url,
            STATUS_NO_CONTRACTS if not contracts else STATUS_SUCCEEDED,
            contracts,
            html=response.text,
            source_code=CAPWAGES_SOURCE,
        )
        if result.covers_target:
            return result
        return replace(result, status=STATUS_NO_MATCHING_CONTRACTS)
    return last_result or ProfileResult(
        candidate,
        f"{CAPWAGES_BASE_URL}/players/{slug}",
        STATUS_NOT_FOUND,
        source_code=CAPWAGES_SOURCE,
    )


def _fetch_profile_with_fallback(
    session: requests.Session,
    candidate: Candidate,
) -> ProfileResult:
    primary = _fetch_profile(session, candidate)
    if primary.covers_target or not candidate.nhl_id:
        return primary
    fallback = _fetch_capwages_profile(session, candidate)
    if fallback.covers_target:
        return replace(
            fallback,
            fallback_attempted=True,
            primary_status=primary.status,
            fallback_status=fallback.status,
        )
    return replace(
        primary,
        fallback_attempted=True,
        primary_status=primary.status,
        fallback_status=fallback.status,
    )


def _candidate_snapshot(**kwargs: Any) -> tuple[list[Candidate], dict[str, Any]]:
    with database_transaction() as connection:
        cursor = connection.cursor()
        candidates = select_candidates(cursor, **kwargs)
        cursor.close()
    return candidates, {"candidate_player_seasons": sum(len(item.missing_seasons) for item in candidates), "candidate_players": len(candidates)}


def _fetch_profiles(session: requests.Session, candidates: list[Candidate], workers: int) -> list[ProfileResult]:
    results: list[ProfileResult] = []
    with ThreadPoolExecutor(max_workers=min(workers, max(1, len(candidates)))) as executor:
        futures = {
            executor.submit(_fetch_profile_with_fallback, session, candidate): candidate
            for candidate in candidates
            if candidate.nhl_id
        }
        for future in as_completed(futures):
            results.append(future.result())
    return results


def _result_source_payload(result: ProfileResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "error": result.error,
        "url": result.url,
        "contracts": [asdict(contract) for contract in result.contracts],
    }


def _source_records_by_code(
    candidates: Iterable[Candidate],
    results: Iterable[ProfileResult],
) -> dict[str, list[tuple[Candidate, dict[str, Any]]]]:
    grouped: dict[str, list[tuple[Candidate, dict[str, Any]]]] = {
        CAPSPACE_SOURCE: [
            (candidate, {"status": STATUS_NO_NHL_ID})
            for candidate in candidates
            if candidate.nhl_id is None
        ]
    }
    for result in results:
        grouped.setdefault(result.source_code, []).append(
            (result.candidate, _result_source_payload(result))
        )
    return grouped


def _persist_successful_results(
    cursor,
    results: Iterable[ProfileResult],
    source_ids: dict[str, int],
    summary: Counter[str],
    context: _PersistenceContext,
    *,
    first_season: int,
    last_season: int,
    preview: bool,
) -> None:
    for result in results:
        if result.status != STATUS_SUCCEEDED:
            continue
        _persist_contracts(
            cursor,
            result.candidate.player_id,
            result.candidate.nhl_id or "",
            result.contracts,
            first_season,
            last_season,
            source_ids[result.source_code],
            summary,
            target_seasons=result.candidate.missing_seasons,
            preview=preview,
            source_code=result.source_code,
            context=context,
        )


def _persist_batch(
    candidates: list[Candidate],
    results: list[ProfileResult],
    *,
    dry_run: bool,
    first_season: int,
    last_season: int,
) -> Counter[str]:
    batch_summary: Counter[str] = Counter()
    with database_transaction() as connection:
        cursor = connection.cursor()
        source_ids = {
            source_code: _source_id(cursor, source_code)
            for source_code in {result.source_code for result in results}
            | {CAPSPACE_SOURCE}
        }
        if not dry_run:
            for source_code, source_records in _source_records_by_code(
                candidates, results
            ).items():
                _source_records_bulk(
                    cursor,
                    source_ids[source_code],
                    source_code,
                    source_records,
                )
        successful_results = [
            result for result in results if result.status == STATUS_SUCCEEDED
        ]
        if successful_results:
            context = _load_persistence_context(
                cursor, first_season, last_season
            )
            _persist_successful_results(
                cursor,
                successful_results,
                source_ids,
                batch_summary,
                context,
                first_season=first_season,
                last_season=last_season,
                preview=dry_run,
            )
        cursor.close()
    return batch_summary


def _profile_metrics(results: Iterable[ProfileResult]) -> Counter[str]:
    materialized = list(results)
    return Counter(
        {
            "profiles_succeeded": sum(
                result.status == STATUS_SUCCEEDED for result in materialized
            ),
            "profiles_with_target_coverage": sum(
                result.covers_target for result in materialized
            ),
            "profiles_not_found": sum(
                result.status == STATUS_NOT_FOUND for result in materialized
            ),
            "profiles_failed": sum(
                result.status in FAILURE_STATUSES for result in materialized
            ),
            "profiles_no_contracts": sum(
                result.status == STATUS_NO_CONTRACTS for result in materialized
            ),
            "profiles_no_matching_contracts": sum(
                result.status == STATUS_NO_MATCHING_CONTRACTS
                for result in materialized
            ),
            "capspace_profiles_succeeded": sum(
                result.status == STATUS_SUCCEEDED
                and result.source_code == CAPSPACE_SOURCE
                for result in materialized
            ),
            "capwages_profiles_succeeded": sum(
                result.status == STATUS_SUCCEEDED
                and result.source_code == CAPWAGES_SOURCE
                for result in materialized
            ),
            "capwages_fallbacks_attempted": sum(
                result.fallback_attempted for result in materialized
            ),
            "capwages_fallbacks_failed": sum(
                result.fallback_status in FAILURE_STATUSES
                for result in materialized
            ),
            "capwages_fallbacks_not_found": sum(
                result.fallback_status == STATUS_NOT_FOUND
                for result in materialized
            ),
            "contracts_parsed": sum(
                len(result.contracts) for result in materialized
            ),
        }
    )


def _unprocessed_count(summary: dict[str, Any]) -> int:
    return (
        summary.get("records_skipped", 0)
        + summary.get("players_without_nhl_ids", 0)
        + summary.get("profiles_failed", 0)
        + summary.get("profiles_not_found", 0)
    )


def _run(
    session: requests.Session,
    *,
    dry_run: bool,
    first_season: int = DEFAULT_FIRST_SEASON,
    last_season: int = DEFAULT_LAST_SEASON,
    limit: int | None = None,
    workers: int = 4,
    batch_size: int = DEFAULT_BATCH_SIZE,
    player_id: int | None = None,
    nhl_id: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    if not 1 <= workers <= MAX_WORKERS:
        raise ValueError(f"workers must be between 1 and {MAX_WORKERS}")
    if not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise ValueError(f"batch_size must be between 1 and {MAX_BATCH_SIZE}")
    candidates, summary = _candidate_snapshot(
        first_season=first_season,
        last_season=last_season,
        limit=limit,
        player_id=player_id,
        nhl_id=nhl_id,
        force=force,
    )
    summary.update(
        {
            "players_without_nhl_ids": sum(
                item.nhl_id is None for item in candidates
            ),
            "profiles_requested": sum(
                item.nhl_id is not None for item in candidates
            ),
        }
    )
    if not candidates:
        summary.update(
            records_read=0,
            records_created=0,
            records_updated=0,
            records_skipped=0,
            remaining_uncovered_player_seasons=0,
        )
        return summary
    aggregate = Counter()
    total_results = 0
    for offset in range(0, len(candidates), batch_size):
        batch = candidates[offset:offset + batch_size]
        results = _fetch_profiles(session, batch, workers)
        total_results += len(results)
        aggregate.update(_profile_metrics(results))
        aggregate.update(
            _persist_batch(
                batch,
                results,
                dry_run=dry_run,
                first_season=first_season,
                last_season=last_season,
            )
        )
        aggregate["batches_processed"] += 1
    summary.update(dict(aggregate))
    summary["profiles_requested"] = total_results
    if dry_run:
        summary.update(
            {
                "proposed_contracts": summary.get("contracts_parsed", 0),
                "records_read": summary["candidate_player_seasons"],
                "records_created": 0,
                "records_updated": 0,
            }
        )
        summary["records_skipped"] = _unprocessed_count(summary)
        return summary
    summary["records_read"] = summary["candidate_player_seasons"] + summary["contracts_parsed"]
    summary["records_created"] = summary.get(
        "contracts_created", 0
    ) + summary.get("contract_seasons_created", 0)
    summary["records_updated"] = summary.get(
        "contracts_matched", 0
    ) + summary.get("contract_seasons_updated", 0)
    summary["records_skipped"] = _unprocessed_count(summary)
    with database_transaction() as connection:
        cursor = connection.cursor()
        coverage = _coverage_counts(cursor, first_season, last_season)
        summary["remaining_uncovered_player_seasons"] = coverage[
            "missing_player_seasons"
        ]
        cursor.close()
    return summary


def _source_id(cursor, source_code: str = CAPSPACE_SOURCE) -> int:
    cursor.execute("SELECT id FROM data_sources WHERE code=%s", (source_code,))
    row = cursor.fetchone()
    if not row:
        raise RuntimeError(
            f"{source_code} source is not registered; run Alembic upgrade head"
        )
    return int(row[0])


def _coverage_counts(cursor, first_season: int, last_season: int) -> dict[str, Any]:
    cursor.execute(
        f"""WITH {STAT_SEASONS_CTE}
            SELECT count(*),
                   count(*) FILTER (WHERE NOT ({MISSING_CONTRACT_PREDICATE}))
              FROM stat_seasons s""",
        (first_season, last_season, first_season, last_season),
    )
    total, covered = cursor.fetchone()
    return {"total_player_seasons": total, "covered_player_seasons": covered, "missing_player_seasons": total - covered, "coverage_pct": round(covered * 100 / total, 2) if total else None}


def coverage_report(*, first_season: int = DEFAULT_FIRST_SEASON, last_season: int = DEFAULT_LAST_SEASON) -> dict[str, Any]:
    with database_transaction() as connection:
        cursor = connection.cursor()
        report = _coverage_counts(cursor, first_season, last_season)
        range_params = (first_season, last_season, first_season, last_season)
        cursor.execute(
            f"""WITH {STAT_SEASONS_CTE}
                SELECT season_start_year,count(*)
                  FROM stat_seasons s
                 WHERE {MISSING_CONTRACT_PREDICATE}
                 GROUP BY season_start_year
                 ORDER BY season_start_year""",
            range_params,
        )
        report["missing_by_season"] = {row[0]: row[1] for row in cursor.fetchall()}
        cursor.execute(
            f"""WITH {STAT_SEASONS_CTE}
                SELECT p.id,p.first_name || ' ' || p.last_name,count(*)
                  FROM stat_seasons s
                  JOIN players p ON p.id=s.player_id
                 WHERE {MISSING_CONTRACT_PREDICATE}
                 GROUP BY p.id,p.first_name,p.last_name
                 ORDER BY count(*) DESC,p.id""",
            range_params,
        )
        report["missing_by_player"] = [{"player_id": row[0], "player": row[1], "count": row[2]} for row in cursor.fetchall()]
        cursor.execute("""SELECT ds.code,payload->>'status',count(*)
            FROM source_records sr JOIN data_sources ds ON ds.id=sr.source_id
            WHERE (ds.code='capspace' AND sr.entity_type='capspace_player_profile')
               OR (ds.code='capwages' AND sr.entity_type='capwages_player_profile')
            GROUP BY ds.code,payload->>'status'""")
        source_outcomes: dict[str, dict[str, int]] = {}
        for source_code, status, count in cursor.fetchall():
            source_outcomes.setdefault(source_code, {})[status] = count
        report["source_outcomes"] = source_outcomes
        cursor.close()
    return report


@tracked_ingestion(CAPSPACE_SOURCE, "populate_historical_contracts")
def ingest_historical_contracts(session: requests.Session, **kwargs: Any) -> dict[str, Any]:
    return _run(session, dry_run=False, **kwargs)


def preview_historical_contracts(session: requests.Session, **kwargs: Any) -> dict[str, Any]:
    return _run(session, dry_run=True, **kwargs)


def existing_historical_contract_summary() -> dict[str, Any]:
    report = coverage_report()
    report.update({"cached": 1, "records_read": report["total_player_seasons"], "records_created": 0, "records_updated": 0, "records_skipped": 0})
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gap-fill historical NHL contracts from CapSpace and CapWages"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="preview without contract/source-record mutations")
    mode.add_argument("--apply", action="store_true", help="persist the backfill")
    mode.add_argument("--coverage", action="store_true", help="print current historical contract coverage and exit")
    parser.add_argument("--nhl-id")
    parser.add_argument("--player-id", type=int)
    parser.add_argument("--first-season", type=int, default=DEFAULT_FIRST_SEASON)
    parser.add_argument("--last-season", type=int, default=DEFAULT_LAST_SEASON)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help=f"players fetched and committed per batch (1-{MAX_BATCH_SIZE})")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    init_db()
    if args.coverage:
        print(json.dumps(coverage_report(first_season=args.first_season, last_season=args.last_season), indent=2, sort_keys=True, default=str))
        return 0
    session = http_session()
    options = {"first_season": args.first_season, "last_season": args.last_season, "limit": args.limit, "workers": args.workers, "batch_size": args.batch_size, "player_id": args.player_id, "nhl_id": args.nhl_id, "force": args.force}
    summary = ingest_historical_contracts(session, **options) if args.apply else preview_historical_contracts(session, **options)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
