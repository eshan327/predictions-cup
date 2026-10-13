"""Documented GET-only SIG interface. No exchange mutation capability."""

from __future__ import annotations

import os
import random
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable

import httpx


class APIError(RuntimeError):
    """Sanitized API failure; never contains response bodies or credentials."""


class SIGClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        transport: httpx.BaseTransport | None = None,
        interval: float = 0.8,
        retries: int = 3,
        sleep: Callable = time.sleep,
        clock: Callable = time.monotonic,
        capture: Callable | None = None,
    ) -> None:
        self._key = api_key or os.environ.get("SIG_API_KEY")
        if not self._key:
            raise APIError("Set SIG_API_KEY in the environment")
        if interval < 0 or retries < 0:
            raise ValueError("invalid retry/rate settings")
        # Fixed origin prevents accidental credential forwarding to configured hosts.
        self.client = httpx.Client(
            base_url="https://sig.thesuper.market/api/v1",
            timeout=25,
            follow_redirects=False,
            transport=transport,
        )
        self.interval, self.retries = interval, retries
        self.sleep, self.clock, self.capture = sleep, clock, capture
        self._last = float("-inf")

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        if not re.fullmatch(r"/[A-Za-z0-9_/-]+", path) or "//" in path:
            raise ValueError("invalid relative API path")
        for attempt in range(self.retries + 1):
            self.sleep(max(0, self._last + self.interval - self.clock()))
            self._last = self.clock()
            started = datetime.now(timezone.utc).isoformat()
            try:
                r = self.client.get(
                    path, params=params, headers={"Authorization": "Bearer " + self._key}
                )
            except httpx.TransportError:
                if attempt == self.retries:
                    raise APIError("SIG transport failure") from None
                self.sleep(2**attempt + random.random())
                continue
            if r.status_code in (429, 500, 502, 503, 504) and attempt < self.retries:
                retry = r.headers.get("Retry-After", "0")
                try:
                    delay = float(retry)
                except ValueError:
                    try:
                        delay = (
                            parsedate_to_datetime(retry) - datetime.now(timezone.utc)
                        ).total_seconds()
                    except (ValueError, TypeError):
                        delay = 0
                delay = max(delay, 2**attempt + random.random())
                if delay > 60:
                    raise APIError("Server requests backoff over 60s; stop and retry later")
                self.sleep(delay)
                continue
            if r.status_code != 200:
                raise APIError(f"SIG GET failed with HTTP {r.status_code}")
            try:
                body = r.json()
            except ValueError:
                raise APIError("SIG returned non-JSON data") from None
            if not isinstance(body, dict):
                raise APIError("SIG response must be an object")
            if self.capture:
                self.capture(
                    path, params or {}, body, started, datetime.now(timezone.utc).isoformat()
                )
            return body
        raise APIError("retry budget exhausted")

    def pages(self, path: str, *, params: dict | None = None, max_pages: int = 1000):
        query = dict(params or {})
        seen = set()
        for _ in range(max_pages):
            page = self.get(path, params=query)
            if not isinstance(page.get("data"), list):
                raise APIError("missing paginated data")
            if page.get("coverage", {}).get("complete") is False:
                raise APIError("incomplete history coverage")
            yield page
            paging = page.get("pagination", {})
            if not isinstance(paging.get("hasMore"), bool):
                raise APIError("missing pagination completeness")
            if not paging["hasMore"]:
                return
            cursor = paging.get("nextCursor")
            if cursor:
                token = str(cursor)
                query["cursor"] = cursor
            elif "offset" in paging and isinstance(paging.get("limit"), int):
                token = str(paging["offset"] + paging["limit"])
                query["offset"] = int(token)
            else:
                raise APIError("pagination hasMore without continuation")
            if token in seen or not page["data"]:
                raise APIError("non-progressing pagination")
            seen.add(token)
        raise APIError("pagination limit reached; result is incomplete")

    def rows(self, path: str, *, params: dict | None = None) -> list[dict]:
        return [row for page in self.pages(path, params=params) for row in page["data"]]

    def get_orderbook(self, exchange_id: str, tournament_id: str) -> dict:
        if not str(exchange_id).isdigit():
            raise ValueError("numeric exchange ID required")
        return self.get(
            f"/exchanges/{exchange_id}/orderbook",
            params={"tournamentId": tournament_id, "depth": 200},
        )
