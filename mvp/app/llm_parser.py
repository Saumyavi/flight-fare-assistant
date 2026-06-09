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


SYSTEM_PROMPT = """You parse short WhatsApp messages for a flight fare alert bot.
Today's date is {today}. Default currency is {currency}.
Return strict JSON matching the schema. Rules:
- Resolve relative dates ("next weekend", "first week of June") into concrete YYYY-MM-DD ranges.
- If only one date is given, set depart_from == depart_to.
- If user says "one way", leave return_* null.
- Prices like "5k", "₹5000", "INR 5000", "Rs. 5k" -> numeric in default currency.
- intent="create_watch" only when origin, destination, dates, and price are all derivable.
- intent="list"/"pause"/"resume"/"stop" for commands ("list", "pause 3", "stop all"). watch_id optional.
- intent="help" for greetings or "help".
- intent="unknown" if you can't tell.
- Do NOT invent IATA codes; put the city as the user wrote it in origin_text/destination_text.
"""


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
