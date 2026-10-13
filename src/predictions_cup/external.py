"""Public RTWH Senate widget adapter, verified 2026-10-13.

Archives full source responses locally. Imported probabilities are observations,
not calibrated truth. No SIG credential is ever sent to an external source.
"""

import hashlib
import json
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from predictions_cup.models import timestamp

RTWH_PAGE = "https://www.racetothewh.com/senate/26"
RTWH_DATA = "https://live-data.jifo.co/6911ecb8-c744-4464-a182-70568e288364"


def percentage(text):
    match = re.search(r"(\d+(?:\.\d+)?)%", str(text))
    if not match:
        raise ValueError("missing forecast percentage")
    result = float(match[1]) / 100
    if not 0 <= result <= 1:
        raise ValueError("invalid percentage")
    return result


def parse_rtwh(body, observed_at):
    sheets = body["data"]
    chamber = next(
        (
            s
            for s in sheets
            if len(s) > 1
            and s[0] == ["", "Democrats", "Republicans"]
            and s[1][0] == "Chance to Win"
        ),
        None,
    )
    races = next((s for s in sheets if s and s[0] == ["", "D", "R", "Ind"]), None)
    updates = [
        s[0][0]
        for s in sheets
        if s and s[0] and isinstance(s[0][0], str) and s[0][0].startswith("Last Updated on ")
    ]
    if chamber is None or races is None or len(updates) != 1:
        raise ValueError("RTWH schema changed")
    observed = datetime.fromtimestamp(observed_at, ZoneInfo("America/New_York"))
    update = updates[0].removeprefix("Last Updated on ").removesuffix(" ET")
    published = datetime.strptime(f"{observed.year} {update}", "%Y %b %d, %I:%M %p").replace(
        tzinfo=ZoneInfo("America/New_York")
    )
    if published > observed + timedelta(minutes=1):
        raise ValueError("source timestamp is in the future")
    if observed - published > timedelta(days=3):
        raise ValueError("stale source forecast")
    output = {"Senate/D": percentage(chamber[1][1]), "Senate/R": percentage(chamber[1][2])}
    if abs(output["Senate/D"] + output["Senate/R"] - 1) > 0.002:
        raise ValueError("chamber probabilities inconsistent")
    for row in races[1:]:
        if row[0].startswith("Special "):
            continue
        for party, value in zip(["D", "R", "I"], row[1:]):
            if value:
                output[f"{row[0]}/{party}"] = percentage(value)
    return {
        "published_at": published.timestamp(),
        "observed_at": observed_at,
        "probabilities": output,
        "source_url": RTWH_PAGE,
        "artifact_sha256": hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest(),
    }


def fetch_rtwh(store):
    started = datetime.now(ZoneInfo("UTC")).isoformat()
    # Public linked data endpoint: no cookies, no SIG client, no authentication.
    with httpx.Client(timeout=25, follow_redirects=False) as client:
        response = client.get(RTWH_DATA)
        response.raise_for_status()
        body = response.json()
    received = datetime.now(ZoneInfo("UTC")).isoformat()
    store.capture("/external/rtwh/senate", {"url": RTWH_DATA}, body, started, received)
    return parse_rtwh(body, timestamp(received))
