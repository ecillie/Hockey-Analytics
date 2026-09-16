import sys
import os
import json
import re
from decimal import Decimal

import requests
from sqlalchemy.orm import Session

from app.database import SessionLocal, init_db
from app.models import Player, Contract, PlayerSalary
from app.ScriptingFiles.FullDataScript.save_contracts_to_db import (
    build_slug_lookup_from_active_players,
    create_slug_from_name,
    headers,
)

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


# DB_HOST=localhost python3 -m app.ScriptingFiles.save_individual_contract_years

SALARY_CAP = {
    "2005": Decimal("39000000"),
    "2006": Decimal("44000000"),
    "2007": Decimal("50300000"),
    "2008": Decimal("56700000"),
    "2009": Decimal("56800000"),
    "2010": Decimal("59400000"),
    "2011": Decimal("64300000"),
    "2012": Decimal("70200000"),
    "2013": Decimal("64300000"),
    "2014": Decimal("69000000"),
    "2015": Decimal("71400000"),
    "2016": Decimal("73000000"),
    "2017": Decimal("75000000"),
    "2018": Decimal("79500000"),
    "2019": Decimal("81500000"),
    "2020": Decimal("81500000"),
    "2021": Decimal("81500000"),
    "2022": Decimal("82500000"),
    "2023": Decimal("82500000"),
    "2024": Decimal("88000000"),
    "2025": Decimal("95500000"),
    "2026": Decimal("104000000")
}


def parse_money(money_str: str) -> Decimal:
    """Parses '$836,667' style strings into Decimal."""
    if not money_str:
        return Decimal("0")
    cleaned = str(money_str).replace("$", "").replace(",", "").replace(" ", "").strip()
    if cleaned in {"", "-", "–"}:
        return Decimal("0")
    try:
        return Decimal(cleaned)
    except Exception:
        return Decimal("0")


def season_to_year(season: str):
    """Converts '2023-24' -> 2023."""
    if not season or "-" not in season:
        return None
    try:
        return int(str(season).split("-")[0])
    except Exception:
        return None


def is_slide_detail(detail: dict) -> bool:
    """Detect ELC slide rows from CapWages detail row."""
    base_salary = str(detail.get("baseSalary", "")).upper()
    return "SLIDE" in base_salary


def scrape_player_contract_details(slug: str):
    """
    Returns contract blocks including raw details rows from CapWages player page.
    Each item has: start_year, end_year, duration, team, cap_hit, details
    """
    if not slug:
        return []

    url = f"https://capwages.com/players/{slug}"
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()

    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        resp.text,
        re.DOTALL,
    )
    if not match:
        return []

    data = json.loads(match.group(1))
    contracts_array = (
        data.get("props", {})
        .get("pageProps", {})
        .get("player", {})
        .get("contracts", [])
    )

    parsed = []
    for c in contracts_array:
        if not isinstance(c, dict):
            continue
        details = c.get("details", [])
        if not details:
            continue

        first = details[0]
        last = details[-1]
        first_year = season_to_year(first.get("season"))
        last_year = season_to_year(last.get("season"))
        if first_year is None or last_year is None:
            continue

        parsed.append(
            {
                "team": c.get("signingTeam", ""),
                "start_year": first_year,
                "end_year": last_year,
                "duration": len(details),
                "cap_hit": parse_money(first.get("capHit", "")),
                "details": details,
            }
        )

    return parsed


def match_scraped_contract(db_contract: Contract, scraped_contracts: list, used_idxs: set):
    """
    Match DB contract to one scraped contract block.
    Priority:
    1) exact start_year + duration + unused
    2) exact start_year + unused
    3) best score by year/duration/cap_hit among unused
    """
    # 1) exact start + duration
    for i, sc in enumerate(scraped_contracts):
        if i in used_idxs:
            continue
        if sc["start_year"] == db_contract.start_year and sc["duration"] == db_contract.duration:
            used_idxs.add(i)
            return sc

    # 2) exact start
    for i, sc in enumerate(scraped_contracts):
        if i in used_idxs:
            continue
        if sc["start_year"] == db_contract.start_year:
            used_idxs.add(i)
            return sc

    # 3) best fallback
    best_idx = None
    best_score = 10**9
    db_cap = Decimal(str(db_contract.cap_hit)) if db_contract.cap_hit is not None else Decimal("0")

    for i, sc in enumerate(scraped_contracts):
        if i in used_idxs:
            continue
        year_delta = abs(sc["start_year"] - db_contract.start_year)
        dur_delta = abs(sc["duration"] - db_contract.duration)
        cap_delta = abs(sc["cap_hit"] - db_cap)
        score = (year_delta * 1_000_000) + (dur_delta * 100_000) + int(cap_delta)
        if score < best_score:
            best_score = score
            best_idx = i

    if best_idx is not None:
        used_idxs.add(best_idx)
        return scraped_contracts[best_idx]

    return None


def make_player_salary_kwargs(player_id, contract_id, year, cap_hit, cap_pct, is_slide):
    kwargs = {
        "player_id": player_id,
        "contract_id": contract_id,
        "year": year,
        "cap_hit": cap_hit,
        "cap_pct": cap_pct,
    }
    # Works even if you haven't added is_slide yet.
    if hasattr(PlayerSalary, "is_slide"):
        kwargs["is_slide"] = is_slide
    return kwargs


def save_individual_contract_years():
    init_db()
    db: Session = SessionLocal()

    created = 0
    updated = 0
    skipped = 0

    try:
        # Build slug map once (handles accents better than manual slugify)
        try:
            slug_lookup = build_slug_lookup_from_active_players()
        except Exception:
            slug_lookup = {}

        # Load all players + contracts once
        players = db.query(Player).all()
        player_by_id = {p.id: p for p in players}
        all_contracts = db.query(Contract).all()

        # Cache each player's CapWages contract blocks
        details_cache = {}

        for contract in all_contracts:
            player = player_by_id.get(contract.player_id)
            if not player:
                skipped += 1
                continue

            key = f"{player.firstname.upper()} {player.lastname.upper()}"
            slug = slug_lookup.get(key)
            if not slug:
                slug = create_slug_from_name(player.firstname, player.lastname)

            if slug not in details_cache:
                try:
                    details_cache[slug] = scrape_player_contract_details(slug)
                except Exception:
                    details_cache[slug] = []

            scraped_contracts = details_cache.get(slug, [])
            if not scraped_contracts:
                skipped += 1
                continue

            # Keep per-player used set so repeated DB contracts map uniquely
            used_key = f"{contract.player_id}:{slug}"
            if "_used_map" not in details_cache:
                details_cache["_used_map"] = {}
            used_map = details_cache["_used_map"]
            used_idxs = used_map.setdefault(used_key, set())

            matched = match_scraped_contract(contract, scraped_contracts, used_idxs)
            if not matched:
                skipped += 1
                continue

            for detail in matched["details"]:
                year = season_to_year(detail.get("season", ""))
                if year is None:
                    skipped += 1
                    continue

                slide = is_slide_detail(detail)
                cap_hit = Decimal("0") if slide else parse_money(detail.get("capHit", ""))

                salary_cap = SALARY_CAP.get(str(year))
                cap_pct = (
                    (cap_hit / salary_cap) if (salary_cap is not None and salary_cap > 0) else Decimal("0")
                )

                existing = (
                    db.query(PlayerSalary)
                    .filter(
                        PlayerSalary.contract_id == contract.id,
                        PlayerSalary.year == year,
                    )
                    .first()
                )

                if existing:
                    existing.cap_hit = cap_hit
                    existing.cap_pct = cap_pct
                    if hasattr(existing, "is_slide"):
                        existing.is_slide = slide
                    updated += 1
                else:
                    ps = PlayerSalary(
                        **make_player_salary_kwargs(
                            player_id=contract.player_id,
                            contract_id=contract.id,
                            year=year,
                            cap_hit=cap_hit,
                            cap_pct=cap_pct,
                            is_slide=slide,
                        )
                    )
                    db.add(ps)
                    created += 1

        db.commit()
        print(f"player_salaries upsert complete: created={created}, updated={updated}, skipped={skipped}")

    except Exception:
        db.rollback()
        import traceback
        traceback.print_exc()
    finally:
        db.close()
