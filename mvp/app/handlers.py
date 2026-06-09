"""Convert a parsed message into a DB action and produce a reply string."""
from __future__ import annotations

import logging
import re
from datetime import date
from typing import Optional

from sqlmodel import func, select

from .airports import resolve_iata
from .config import settings
from .db import User, Watch, get_session
from .llm_parser import ParsedWatch, generate_reply, parse_message

logger = logging.getLogger(__name__)

HELP_TEXT = (
    "✈️ *Flight Fare Bot*\n"
    "Send something like:\n"
    "  _Track DEL to GOA, under 4000, 5-15 June_\n"
    "  _Mumbai → Dubai return 1-10 Aug, budget 18k_\n\n"
    "Commands:\n"
    "  *LIST* – show your active watches\n"
    "  *PAUSE <id>* / *RESUME <id>* / *STOP <id>*\n"
    "  *STOP ALL* – delete every watch\n"
)

_CMD_RE = re.compile(
    r"^(LIST|HELP|PAUSE|RESUME|STOP)(\s+ALL|\s+\d+)?$",
    re.IGNORECASE,
)


def _get_or_create_user(whatsapp_number: str) -> User:
    with get_session() as s:
        u = s.exec(select(User).where(User.whatsapp_number == whatsapp_number)).first()
        if u:
            return u
        u = User(whatsapp_number=whatsapp_number)
        s.add(u)
        s.commit()
        s.refresh(u)
        return u


def _format_watch(w: Watch) -> str:
    rng = f"{w.depart_from} → {w.depart_to}"
    if w.return_from:
        rng += f" / ret {w.return_from} → {w.return_to}"
    state = "" if w.active else " (paused)"
    return f"#{w.id} {w.origin}→{w.destination}  ≤{int(w.max_price)} {w.currency}  {rng}{state}"


def _list_watches(user_id: int) -> str:
    with get_session() as s:
        watches = s.exec(select(Watch).where(Watch.user_id == user_id)).all()
    if not watches:
        return "You have no active watches. Send a route + budget to start."
    return "Your watches:\n" + "\n".join(_format_watch(w) for w in watches)


def _try_parse_command(upper: str) -> Optional[ParsedWatch]:
    """Parse simple keyword commands without calling the LLM."""
    m = _CMD_RE.match(upper.strip())
    if not m:
        return None
    cmd, arg = m.group(1).upper(), (m.group(2) or "").strip()
    if cmd == "LIST":
        return ParsedWatch(intent="list")
    if cmd == "HELP":
        return ParsedWatch(intent="help")
    if cmd in {"PAUSE", "RESUME", "STOP"}:
        if arg.upper() == "ALL":
            return ParsedWatch(intent=cmd.lower(), watch_id=None)
        watch_id = int(arg) if arg.isdigit() else None
        return ParsedWatch(intent=cmd.lower(), watch_id=watch_id)
    return None


def handle_inbound(whatsapp_number: str, text: str) -> str:
    user = _get_or_create_user(whatsapp_number)
    stripped = text.strip()

    if not stripped:
        return HELP_TEXT

    parsed = _try_parse_command(stripped.upper()) or parse_message(stripped)

    if parsed.intent == "help":
        return HELP_TEXT

    if parsed.intent == "list":
        return _list_watches(user.id)

    if parsed.intent in {"pause", "resume", "stop"}:
        return _mutate_watch(user.id, parsed)

    if parsed.intent == "create_watch":
        return _create_watch(user.id, parsed)

    return generate_reply(text)


def _mutate_watch(user_id: int, p: ParsedWatch) -> str:
    with get_session() as s:
        if p.watch_id is None and p.intent == "stop":
            watches = s.exec(select(Watch).where(Watch.user_id == user_id)).all()
            count = len(watches)
            for w in watches:
                s.delete(w)
            s.commit()
            return f"Deleted {count} watch(es)."

        if p.watch_id is None:
            return "Please specify the watch id, e.g. *PAUSE 3*. Use *LIST* to see them."

        w = s.get(Watch, p.watch_id)
        if not w or w.user_id != user_id:
            return f"No watch #{p.watch_id} found."

        if p.intent == "pause":
            w.active = False
            s.add(w)
            s.commit()
            return f"Watch #{p.watch_id} paused."
        elif p.intent == "resume":
            w.active = True
            s.add(w)
            s.commit()
            return f"Watch #{p.watch_id} resumed."
        elif p.intent == "stop":
            s.delete(w)
            s.commit()
            return f"Deleted watch #{p.watch_id}."

    return f"OK, watch #{p.watch_id} updated."


def _create_watch(user_id: int, p: ParsedWatch) -> str:
    origin = resolve_iata(p.origin_text or "")
    dest = resolve_iata(p.destination_text or "")
    if not origin or not dest:
        return (
            f"I couldn't resolve the airports ('{p.origin_text}' → '{p.destination_text}').\n"
            "Try 3-letter IATA codes like DEL, BOM, GOI."
        )
    if not p.depart_from or not p.depart_to or not p.max_price:
        return "I need a departure date range and a max price. Example: _DEL to GOI 5-15 June under 4000_."

    today = date.today()
    if p.depart_from < today:
        return "The departure date is in the past. Please use a future date."

    if p.depart_to < p.depart_from:
        p.depart_to = p.depart_from

    with get_session() as s:
        count = s.exec(
            select(func.count(Watch.id)).where(Watch.user_id == user_id, Watch.active == True)  # noqa: E712
        ).one()
        if count >= settings.MAX_WATCHES_PER_USER:
            return (
                f"You have {count} active watches (max {settings.MAX_WATCHES_PER_USER}). "
                "Use *STOP <id>* to remove one first."
            )

        w = Watch(
            user_id=user_id,
            origin=origin,
            destination=dest,
            depart_from=p.depart_from,
            depart_to=p.depart_to,
            return_from=p.return_from,
            return_to=p.return_to,
            max_price=float(p.max_price),
            currency=(p.currency or settings.DEFAULT_CURRENCY).upper(),
            adults=p.adults or 1,
        )
        s.add(w)
        s.commit()
        s.refresh(w)
        watch_id = w.id
        max_price = int(w.max_price)
        currency = w.currency
        depart_from = w.depart_from
        depart_to = w.depart_to

    return (
        f"✅ Watching {origin}→{dest} for ≤ {max_price} {currency}.\n"
        f"Departure window: {depart_from} → {depart_to}.\n"
        f"I'll ping you when fares drop. (watch #{watch_id})"
    )
