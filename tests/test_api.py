import httpx
import pytest

from predictions_cup.api import APIError, SIGClient


def client(handler, **kwargs):
    return SIGClient(
        api_key="test-only",
        transport=httpx.MockTransport(handler),
        interval=0,
        sleep=lambda _: None,
        **kwargs,
    )


def test_auth_scope_and_get_only():
    def handler(r):
        assert r.method == "GET"
        assert (
            str(r.url)
            == "https://sig.thesuper.market/api/v1/exchanges/843/orderbook?tournamentId=t&depth=200"
        )
        assert r.headers["Authorization"] == "Bearer test-only"
        return httpx.Response(200, json={"ok": True})

    with client(handler) as c:
        assert c.get_orderbook("843", "t") == {"ok": True}
        assert not hasattr(c, "post")
        for path in ["//evil.com", "https://evil.com", "/../../x", "/x?secret=y", "/x#y"]:
            with pytest.raises(ValueError):
                c.get(path)


def test_retry_after_and_sanitized_errors():
    calls, sleeps = [], []

    def handler(r):
        calls.append(r)
        return httpx.Response(
            429 if len(calls) == 1 else 200, headers={"Retry-After": "3"}, json={"data": []}
        )

    with client(handler) as c:
        c.sleep = sleeps.append
        assert c.get("/markets") == {"data": []}
    assert 3 in sleeps
    with client(lambda _: httpx.Response(403, text="test-only")) as c:
        with pytest.raises(APIError) as e:
            c.get("/account")
        assert "test-only" not in str(e.value)


def test_pagination_and_fail_closed():
    seen = []

    def handler(r):
        seen.append(r.url.params.get("cursor"))
        last = len(seen) == 2
        return httpx.Response(
            200,
            json={
                "data": [{"id": len(seen)}],
                "pagination": {"hasMore": not last, "nextCursor": None if last else "next"},
            },
        )

    with client(handler) as c:
        assert c.rows("/orders") == [{"id": 1}, {"id": 2}]
    assert seen == [None, "next"]
    for body in [
        {"data": [], "pagination": {"hasMore": True}},
        {"data": [], "pagination": {"hasMore": False}, "coverage": {"complete": False}},
        {"data": [], "pagination": {}},
    ]:
        with client(lambda _, b=body: httpx.Response(200, json=b)) as c:
            with pytest.raises(APIError):
                c.rows("/orders")


def test_retry_limit():
    calls = []

    def handler(r):
        calls.append(r)
        return httpx.Response(503)

    with client(handler, retries=2) as c:
        with pytest.raises(APIError):
            c.get("/account")
    assert len(calls) == 3
