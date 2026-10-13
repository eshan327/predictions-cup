"""Conservative API adapter; inspect exact schema before integrating live trading.

Read calls only. No trading endpoint is implemented intentionally.
Never log Authorization headers or raw credentials.
"""
from __future__ import annotations

import os
from typing import Any
import httpx


class APIError(RuntimeError):
    pass


class SIGClient:
    def __init__(self, *, api_key: str | None = None, base_url: str | None = None) -> None:
        self.api_key = api_key or os.getenv("SIG_API_KEY")
        self.base_url = (base_url or os.getenv(
            "SIG_API_BASE", "https://sig.thesuper.market/api/v1"
        )).rstrip("/")
        self.client = httpx.Client(timeout=12.0)

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "SIGClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        """Read-only network request. Authentication convention MUST be verified.

        Bearer is tentative; do not assume the documented endpoint's schema.
        The platform's Scalar reference is the source of truth.
        """
        if not path.startswith("/") or path.startswith("//") or "://" in path:
            raise ValueError("path must be a relative API path")
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        try:
            response = self.client.get(self.base_url + path, params=params, headers=headers)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise APIError(
                "SIG read request failed. Check the endpoint and authentication "
                "scheme in the official Scalar API reference."
            ) from exc

    def discover_markets(self, **params: Any) -> Any:
        """Candidate endpoint from API navigation; verify response before parsing."""
        return self.get("/markets", params=params)

    def get_market(self, market_id: str) -> Any:
        if not market_id or "/" in market_id:
            raise ValueError("invalid market id")
        return self.get("/markets/" + market_id)

    def get_orderbook(self, market_id: str) -> Any:
        """Candidate route, unverified: inspect Scalar's Get market orderbook."""
        if not market_id or "/" in market_id:
            raise ValueError("invalid market id")
        return self.get("/markets/" + market_id + "/orderbook")

    def bulk_prices(self, exchange_ids: list[str]) -> Any:
        """Confirmed path; exact response schema to be verified in API reference."""
        if not 1 <= len(exchange_ids) <= 100:
            raise ValueError("1..100 exchange IDs required")
        return self.get("/exchanges/prices", params={"ids": ",".join(exchange_ids)})
