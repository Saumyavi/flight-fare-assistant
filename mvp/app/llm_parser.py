"""LLM-based message parser using OpenAI structured outputs.

Works with any OpenAI-compatible endpoint (OpenAI, Groq, Ollama, Together, etc.)
configured via OPENAI_BASE_URL / OPENAI_MODEL.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Literal, Optional

from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

from .config import settings

logger = logging.getLogger(__name__)


class ParsedWatch(BaseModel):
    intent: Literal["create_watch", "list", "pause", "resume", "stop", "help", "unknown"]
    origin_text: Optional[str] = Field(None, description="City or airport name as the user wrote it")
    destination_text: Optional[str] = None
    depart_from: Optional[date] = None
    depart_to: Optional[date] = None
    return_from: Optional[date] = None
    return_to: Optional[date] = None
    max_price: Optional[float] = None
    currency: Optional[str] = None
    adults: Optional[int] = 1
    watch_id: Optional[int] = Field(None, description="Watch id when user references a specific watch")
    notes: Optional[str] = None


_client: Optional[OpenAI] = None


def _client_lazy() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL)
    return _client


SYSTEM_PROMPT = """You are a parser for a flight fare alert WhatsApp bot. Today: {today}. Currency: {currency}.

Respond with ONLY a JSON object using exactly these fields:
{{"intent":"create_watch","origin_text":"DEL","destination_text":"GOI","depart_from":"2026-07-01","depart_to":"2026-07-15","return_from":null,"return_to":null,"max_price":4000.0,"currency":"INR","adults":1,"watch_id":null}}

Rules:
- origin_text / destination_text: copy exactly what the user wrote (e.g. "DEL", "Delhi", "Mumbai"). Never null for create_watch.
- intent="create_watch" when origin, destination, dates AND price are all present.
- intent="list"/"pause"/"resume"/"stop" for those commands; set watch_id if user gives a number.
- intent="help" for greetings or the word "help".
- intent="unknown" if unclear.
- Resolve relative dates to YYYY-MM-DD ranges. Single date → depart_from == depart_to.
- Prices: "5k", "₹5000", "Rs 5k", "18000" → float in default currency.
- One-way → return_from/return_to = null.
"""


FALLBACK_REPLY = (
    "Sorry, I didn't quite get that. Try:\n"
    "  _DEL to GOA under 4000, 5-15 June_\n"
    "Or send *HELP* to see all commands."
)

CHAT_SYSTEM_PROMPT = (
    "You are a friendly WhatsApp flight fare alert bot. "
    "You help users track flight prices and get alerted when fares drop. "
    "The user sent something you couldn't parse as a flight watch command. "
    "Reply naturally and helpfully in 1-2 short sentences. "
    "Guide them to send something like: 'DEL to GOA under 4000 5-15 June', "
    "or use commands: LIST, STOP <id>, PAUSE <id>, RESUME <id>, HELP. "
    "Keep it conversational — no markdown, no bullet points."
)


def generate_reply(text: str) -> str:
    """Generate a natural conversational reply for unrecognised messages."""
    try:
        resp = _client_lazy().chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": CHAT_SYSTEM_PROMPT},
                {"role": "user", "content": text.strip()[:2000]},
            ],
            temperature=0.7,
            max_tokens=120,
        )
        return resp.choices[0].message.content.strip() or FALLBACK_REPLY
    except Exception as e:
        logger.error("generate_reply failed: %s", e)
        return FALLBACK_REPLY


def parse_message(text: str) -> ParsedWatch:
    today = date.today().isoformat()
    msgs = [
        {"role": "system", "content": SYSTEM_PROMPT.format(today=today, currency=settings.DEFAULT_CURRENCY)},
        {"role": "user", "content": text.strip()[:2000]},
    ]
    raw = "{}"
    try:
        resp = _client_lazy().chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=msgs,
            response_format={"type": "json_object"},
            temperature=0,
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
        return ParsedWatch.model_validate(data)
    except ValidationError as e:
        logger.warning("LLM schema mismatch: %s | raw=%s", e, raw)
        return ParsedWatch(intent="unknown", notes=f"schema_error: {e}")
    except Exception as e:
        logger.error("parse_message failed: %s", e)
        return ParsedWatch(intent="unknown", notes=f"parse_error: {e}")
