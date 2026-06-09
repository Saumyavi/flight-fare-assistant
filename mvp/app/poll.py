"""Price-poll logic — invoked by the /cron/poll endpoint."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import delete as sa_delete
from sqlmodel import select

from .config import settings
from .db import PriceSample, User, Watch, _utcnow, get_session
from .flights_client import cheapest_across_window
from .whatsapp import send_whatsapp

logger = logging.getLogger(__name__)


def _expire_stale_watches() -> None:
    today = date.today()
    with get_session() as s:
        stale = s.exec(select(Watch).where(Watch.depart_to < today)).all()
        if not stale:
            return
        for w in stale:
            s.delete(w)
        s.commit()
        logger.info("Expired %d stale watch(es)", len(stale))


def _purge_old_samples() -> None:
    cutoff = _utcnow() - timedelta(days=settings.PRICE_SAMPLE_RETENTION_DAYS)
    with get_session() as s:
        result = s.execute(sa_delete(PriceSample).where(PriceSample.sampled_at < cutoff))
        if result.rowcount:
            s.commit()
            logger.info("Purged %d old price sample(s)", result.rowcount)


def poll_once() -> None:
    logger.info("Poll tick @ %s", _utcnow().isoformat())
    _expire_stale_watches()
    _purge_old_samples()

    with get_session() as s:
        watches = list(s.exec(select(Watch).where(Watch.active == True)).all())  # noqa: E712

    logger.info("Checking %d active watch(es)", len(watches))
    for w in watches:
        try:
            _check_watch(w)
        except Exception as e:
            logger.error("Watch #%d failed: %s", w.id, e)


def _check_watch(w: Watch) -> None:
    quote = cheapest_across_window(
        origin=w.origin,
        destination=w.destination,
        depart_from=w.depart_from,
        depart_to=w.depart_to,
        return_from=w.return_from,
        return_to=w.return_to,
        adults=w.adults,
        currency=w.currency,
    )

    with get_session() as s:
        db_watch = s.get(Watch, w.id)
        if not db_watch:
            return

        db_watch.last_polled_at = _utcnow()
        s.add(db_watch)

        if not quote:
            s.commit()
            return

        s.add(PriceSample(
            watch_id=db_watch.id,
            price=quote.price,
            currency=quote.currency,
            depart_date=quote.depart_date,
            return_date=quote.return_date,
            deeplink=quote.deeplink,
            raw_carrier=quote.carrier,
        ))

        if quote.price <= db_watch.max_price:
            # Only alert if this is a new lower price than what we last alerted at
            if (
                db_watch.last_alert_price is not None
                and quote.price >= db_watch.last_alert_price
            ):
                s.commit()
                return

            user = s.get(User, db_watch.user_id)
            if not user:
                s.commit()
                return

            ret_str = f" / ret {quote.return_date}" if quote.return_date else ""
            send_whatsapp(
                user.whatsapp_number,
                f"🔥 Fare drop on watch #{db_watch.id}!\n"
                f"{db_watch.origin} → {db_watch.destination}  "
                f"*{int(quote.price)} {quote.currency}* (≤{int(db_watch.max_price)})\n"
                f"Depart {quote.depart_date}{ret_str}\n"
                f"Book: {quote.deeplink}",
            )
            now = _utcnow()
            db_watch.last_alert_at = now
            db_watch.last_alert_price = quote.price
            s.add(db_watch)
            logger.info(
                "Alert sent for watch #%d: %s→%s @ %s %s",
                db_watch.id, db_watch.origin, db_watch.destination,
                int(quote.price), quote.currency,
            )

        s.commit()
