"""Point-in-time forecast inputs; uncertainty bounds are explicit assumptions."""

import hashlib
from typing import Literal

from pydantic import Field, model_validator

from predictions_cup.models import Model


def settlement_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class ForecastRecord(Model):
    exchange_id: str
    tournament: str
    source: str
    source_url: str
    dependency_group: str
    published_at: float
    observed_at: float
    expires_at: float
    probability: float = Field(ge=0, le=1)
    lower: float = Field(ge=0, le=1)
    upper: float = Field(ge=0, le=1)
    settlement_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    kind: Literal["model", "external_market", "judgment"]
    reviewed: bool = False

    @model_validator(mode="after")
    def coherent(self):
        if not self.lower <= self.probability <= self.upper:
            raise ValueError("forecast bounds do not contain estimate")
        if not self.published_at <= self.observed_at < self.expires_at:
            raise ValueError("invalid availability times")
        return self


def estimate_asof(records, *, exchange_id, tournament, now, terms_hash):
    """Latest source revision known then, equally weighted by dependency group.

    Bounds are the envelope across sources, NOT fitted confidence intervals.
    Do not shrink correlated uncertainty by sqrt(number of sources).
    """
    latest = {}
    for r in records:
        if (
            r.exchange_id != exchange_id
            or r.tournament != tournament
            or r.observed_at > now
            or r.published_at > now
        ):
            continue
        if r.source not in latest or r.observed_at > latest[r.source].observed_at:
            latest[r.source] = r
    valid = [
        r
        for r in latest.values()
        if r.reviewed and now < r.expires_at and r.settlement_sha256 == terms_hash
    ]
    if not valid:
        return None
    groups = {}
    for r in valid:
        groups.setdefault(r.dependency_group, []).append(r.probability)
    p = sum(sum(v) / len(v) for v in groups.values()) / len(groups)
    return {
        "probability": p,
        "lower": min(r.lower for r in valid),
        "upper": max(r.upper for r in valid),
        "groups": len(groups),
        "sources": sorted(r.source for r in valid),
        "calibrated": False,
    }
