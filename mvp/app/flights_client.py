"""Duffel flight search wrapper.

Sign up at https://duffel.com — use a test key (duffel_test_...) for dev.
Prices are returned in the airline's quoted currency (INR for domestic Indian routes).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

import httpx

from .config import settings

logger = logging.getLogger(__name__)

DUFFEL_BASE = "https://api.duffel.com"
DUFFEL_VERSION = "v2"


@dataclass
class FlightQuote:
    price: float
    currency: str
    depart_date: date
    return_date: Optional[date]
    carrier: Optional[str]
    deeplink: Optional[str]


def _skyscanner_link(origin: str, dest: str, depart: date, ret: Optional[date]) -> str:
    d = depart.strftime("%y%m%d")
    if ret:
        r = ret.strftime("%y%m%d")
        return f"https://www.skyscanner.net/transport/flights/{origin.lower()}/{dest.lower()}/{d}/{r}/"
    return f"https://www.skyscanner.net/transport/flights/{origin.lower()}/{dest.lower()}/{d}/"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.DUFFEL_API_KEY}",
        "Duffel-Version": DUFFEL_VERSION,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def cheapest_quote(
    origin: str,
    destination: str,
    depart: date,
    ret: Optional[date] = None,
    adults: int = 1,
    currency: str = "INR",
) -> Optional[FlightQuote]:
    if not settings.DUFFEL_API_KEY:
        logger.warning("DUFFEL_API_KEY not set — skipping flight search")
        return None

    slices = [{"origin": origin, "destination": destination, "departure_date": depart.isoformat()}]
    if ret:
        slices.append({"origin": destination, "destination": origin, "departure_date": ret.isoformat()})

    payload = {
        "data": {
            "slices": slices,
            "passengers": [{"type": "adult"} for _ in range(max(1, adults))],
            "cabin_class": "economy",
        }
    }

    try:
        resp = httpx.post(
            f"{DUFFEL_BASE}/air/offer_requests",
            json=payload,
            headers=_headers(),
            params={"return_offers": "true"},
            timeout=30,
        )
        resp.raise_for_status()
        offers = resp.json().get("data", {}).get("offers", [])

        if not offers:
            return None

        offers.sort(key=lambda o: float(o.get("total_amount", 0)))
        best = offers[0]

        carrier = None
        try:
            carrier = best["slices"][0]["segments"][0]["marketing_carrier"]["iata_code"]
        except (KeyError, IndexError):
            pass

        return FlightQuote(
            price=float(best["total_amount"]),
            currency=best.get("total_currency", currency),
            depart_date=depart,
            return_date=ret,
            carrier=carrier,
            deeplink=_skyscanner_link(origin, destination, depart, ret),
        )
    except httpx.HTTPStatusError as e:
        logger.warning("Duffel HTTP error %s→%s on %s: %s", origin, destination, depart, e)
        return None
    except Exception as e:
        logger.error("Duffel unexpected error %s→%s on %s: %s", origin, destination, depart, e)
        return None


def cheapest_across_window(
    origin: str,
    destination: str,
    depart_from: date,
    depart_to: date,
    return_from: Optional[date] = None,
    return_to: Optional[date] = None,
    adults: int = 1,
    currency: str = "INR",
    max_samples: int = settings.MAX_SAMPLES_PER_WATCH,
) -> Optional[FlightQuote]:
    """Sample up to max_samples departure dates across the window."""
    days = (depart_to - depart_from).days
    if days < 0:
        return None
    step = max(1, (days // max(1, max_samples - 1)) or 1)
    candidates: list[date] = []
    d = depart_from
    while d <= depart_to and len(candidates) < max_samples:
        candidates.append(d)
        d = date.fromordinal(d.toordinal() + step)
    if depart_to not in candidates:
        candidates.append(depart_to)

    best: Optional[FlightQuote] = None
    for dep in candidates:
        ret = None
        if return_from and return_to:
            offset = (dep - depart_from).days
            ret_candidate = date.fromordinal(return_from.toordinal() + offset)
            ret_candidate = max(return_from, min(return_to, ret_candidate))
            ret = ret_candidate
        q = cheapest_quote(origin, destination, dep, ret, adults, currency)
        if q and (best is None or q.price < best.price):
            best = q
    return best
