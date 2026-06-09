"""FastAPI app: Twilio webhook + health/cron/debug endpoints."""
from __future__ import annotations

import html
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import text

from .config import settings
from .db import get_session, init_db
from .handlers import handle_inbound
from .poll import poll_once

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Flight Fare Bot", lifespan=lifespan)


async def _verify_twilio_signature(request: Request) -> None:
    if not settings.VALIDATE_TWILIO_SIGNATURE or not settings.TWILIO_AUTH_TOKEN:
        return
    from twilio.request_validator import RequestValidator

    form = dict(await request.form())
    url = settings.WEBHOOK_URL or str(request.url)
    sig = request.headers.get("X-Twilio-Signature", "")
    if not RequestValidator(settings.TWILIO_AUTH_TOKEN).validate(url, form, sig):
        logger.warning("Invalid Twilio signature from %s", request.client)
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")


@app.get("/health")
def health():
    try:
        with get_session() as s:
            s.execute(text("SELECT 1"))
        return JSONResponse({"ok": True, "db": True})
    except Exception as e:
        logger.error("Health check DB ping failed: %s", e)
        return JSONResponse({"ok": False, "db": False}, status_code=503)


@app.post("/twilio/whatsapp", response_class=PlainTextResponse)
async def twilio_webhook(
    request: Request,
    From: str = Form(...),
    Body: str = Form(""),
):
    await _verify_twilio_signature(request)
    reply = handle_inbound(From, Body)
    return f"<?xml version='1.0' encoding='UTF-8'?><Response><Message>{html.escape(reply)}</Message></Response>"


@app.post("/cron/poll")
async def cron_poll(request: Request):
    """Triggered by Vercel Cron. Vercel sends Authorization: Bearer {CRON_SECRET}."""
    if settings.CRON_SECRET:
        if request.headers.get("authorization") != f"Bearer {settings.CRON_SECRET}":
            raise HTTPException(status_code=401)
    poll_once()
    return JSONResponse({"ok": True})


@app.post("/debug/simulate")
async def simulate(request: Request, payload: dict):
    """Disabled unless DEBUG_SECRET is set. Never set this in production."""
    if not settings.DEBUG_SECRET:
        raise HTTPException(status_code=404)
    if request.headers.get("X-Debug-Secret") != settings.DEBUG_SECRET:
        raise HTTPException(status_code=403)
    reply = handle_inbound(payload.get("from", "whatsapp:+910000000000"), payload.get("body", ""))
    return JSONResponse({"reply": reply})
