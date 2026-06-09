"""Twilio WhatsApp sender (uses the free sandbox by default)."""
from __future__ import annotations

import logging

from twilio.rest import Client

from .config import settings

logger = logging.getLogger(__name__)

_client: Client | None = None


def _client_lazy() -> Client:
    global _client
    if _client is None:
        _client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    return _client


def send_whatsapp(to_number: str, body: str) -> str | None:
    """to_number must already be 'whatsapp:+E164'. Returns message SID or None."""
    if not to_number.startswith("whatsapp:"):
        to_number = f"whatsapp:{to_number}"
    try:
        msg = _client_lazy().messages.create(
            from_=settings.TWILIO_WHATSAPP_FROM,
            to=to_number,
            body=body[:1500],
        )
        return msg.sid
    except Exception as e:
        logger.error("WhatsApp send failed to %s: %s", to_number, e)
        return None
