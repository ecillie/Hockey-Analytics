"""Smoke tests for every supported backend and ingestion entrypoint."""

from __future__ import annotations

import ast
import os
from pathlib import Path
import py_compile
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
APP = BACKEND / "app"
FULL_DATA_SCRIPT = APP / "ScriptingFiles" / "FullDataScript"
LEGACY_LOADERS = BACKEND / "legacy_loaders"

SUPPORTED_CLI_MODULES = {
    "app.ScriptingFiles.FullDataScript.populate_roster_status",
    "app.ScriptingFiles.FullDataScript.run_all",
}
QUARANTINED_LOADERS = {
    "save_basic_player_stats.py",
    "save_contracts_to_db.py",
    "save_goalie_advanced_stats.py",
    "save_individual_contract_years.py",
    "save_nhl_regular_seasoe_schedule.py",
    "save_players_to_db.py",
    "save_previous_games_stats.py",
    "save_skater_advanced_stats.py",
}


def supported_python_files() -> list[Path]:
    return sorted(
        path
        for path in APP.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def full_data_modules() -> list[str]:
    return [
        ".".join(path.relative_to(BACKEND).with_suffix("").parts)
        for path in sorted(FULL_DATA_SCRIPT.rglob("*.py"))
        if path.name != "__init__.py" and "__pycache__" not in path.parts
    ]


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def has_main_guard(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if (
            isinstance(test, ast.Compare)
            and isinstance(test.left, ast.Name)
            and test.left.id == "__name__"
            and len(test.ops) == 1
            and isinstance(test.ops[0], ast.Eq)
            and len(test.comparators) == 1
            and isinstance(test.comparators[0], ast.Constant)
            and test.comparators[0].value == "__main__"
        ):
            return True
    return False


def test_complete_backend_application_compiles(tmp_path):
    for source in supported_python_files():
        target = tmp_path / source.relative_to(APP).with_suffix(".pyc")
        target.parent.mkdir(parents=True, exist_ok=True)
        py_compile.compile(str(source), cfile=str(target), doraise=True)


def test_supported_tree_does_not_reference_removed_orm_or_legacy_loaders():
    failures = []
    for source in supported_python_files():
        imports = imported_modules(source)
        forbidden = sorted(
            name
            for name in imports
            if name == "app.models" or ".save_" in name
        )
        if forbidden:
            failures.append(f"{source.relative_to(ROOT)}: {', '.join(forbidden)}")

    assert failures == []
    assert list(FULL_DATA_SCRIPT.glob("save_*.py")) == []


def test_complete_legacy_loader_set_is_quarantined_outside_application_tree():
    archived = {path.name for path in LEGACY_LOADERS.glob("save_*.py")}

    assert archived == QUARANTINED_LOADERS
    assert not any(path.is_relative_to(APP) for path in LEGACY_LOADERS.glob("*.py"))
    assert (LEGACY_LOADERS / "README.md").is_file()


def test_supported_cli_manifest_matches_executable_modules():
    executable_modules = {
        ".".join(path.relative_to(BACKEND).with_suffix("").parts)
        for path in FULL_DATA_SCRIPT.rglob("*.py")
        if has_main_guard(path)
    }
    assert executable_modules == SUPPORTED_CLI_MODULES


@pytest.mark.parametrize("module", full_data_modules())
def test_supported_ingestion_module_imports_in_fresh_interpreter(module):
    environment = os.environ.copy()
    environment.update(
        {
            "ENV": "dev",
            "DATABASE_URL": "postgresql://fixture:fixture@127.0.0.1:9/fixture",
            "PYTHONPATH": str(BACKEND),
        }
    )
    completed = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert completed.returncode == 0, (
        f"failed to import {module}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )
