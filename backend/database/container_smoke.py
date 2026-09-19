"""Validate the externally served API from the built backend container."""

from __future__ import annotations

import argparse
import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


CHECKS = {
    "/api/health": lambda body: body == {"status": "ok"},
    "/api/seasons": lambda body: (
        isinstance(body, dict)
        and bool(body.get("availableSeasons"))
        and isinstance(body.get("currentSeason"), int)
    ),
    "/api/teams": lambda body: isinstance(body, list),
}


def request_json(url: str, timeout: float) -> tuple[int, object, str]:
    try:
        with urlopen(url, timeout=timeout) as response:  # noqa: S310 - caller supplies CI URL
            text = response.read().decode("utf-8")
            return response.status, json.loads(text), text
    except HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        return exc.code, None, text


def validate(base_url: str, *, attempts: int, delay: float, timeout: float) -> None:
    base_url = base_url.rstrip("/")
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            status, body, text = request_json(f"{base_url}/api/health", timeout)
            if status == 200 and CHECKS["/api/health"](body):
                break
            last_error = RuntimeError(f"health returned status={status} body={text}")
        except (URLError, OSError, json.JSONDecodeError) as exc:
            last_error = exc
        if attempt < attempts:
            time.sleep(delay)
    else:
        raise RuntimeError(
            f"container did not become healthy after {attempts} attempts: {last_error}"
        )

    for path, check in CHECKS.items():
        status, body, text = request_json(f"{base_url}{path}", timeout)
        if status != 200 or not check(body):
            raise RuntimeError(
                f"container smoke check failed for {path}: status={status} body={text}"
            )
        print(f"PASS {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--attempts", type=int, default=30)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=2.0)
    arguments = parser.parse_args()
    validate(
        arguments.base_url,
        attempts=arguments.attempts,
        delay=arguments.delay,
        timeout=arguments.timeout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
