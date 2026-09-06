"""Small dependency-free JSON/JSONP HTTP client used by roster loaders."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class JsonHttpClient:
    def __init__(self, timeout_seconds: float = 15.0) -> None:
        self.timeout_seconds = timeout_seconds

    def get_json(
        self,
        url: str,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if params:
            url = f"{url}?{urlencode(params)}"

        request = Request(
            url,
            headers={
                "Accept": "application/json, text/javascript",
                "User-Agent": "TradeValueRosterSync/1.0",
            },
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            body = response.read().decode("utf-8")

        return self._decode_json_or_jsonp(body)

    @staticmethod
    def _decode_json_or_jsonp(body: str) -> dict[str, Any]:
        payload = body.strip()
        if payload.startswith("{"):
            return json.loads(payload)

        opening = payload.find("(")
        closing = payload.rfind(")")
        if opening < 1 or closing <= opening:
            raise ValueError("Response was neither JSON nor JSONP")
        return json.loads(payload[opening + 1 : closing])
