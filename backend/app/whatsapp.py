"""Optional real WhatsApp delivery through the Twilio WhatsApp API.

Disabled unless these environment variables are set (never put them in code or in git):
  TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM  (for the sandbox: +14155238886)

Seeded demo parents carry placeholder numbers (+91 00000 ...) and are NEVER sent to; for those the app
keeps the simulated delivery. A real number is only used when an admin enters one for a student.
"""
from __future__ import annotations
import os
import re

import httpx

API = "https://api.twilio.com/2010-04-01/Accounts"
DEMO_PREFIX = "+9100000"
KEYS = ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_WHATSAPP_FROM")


def configured() -> bool:
    return all(os.environ.get(k) for k in KEYS)


def status() -> dict:
    return {"configured": configured(), "provider": "Twilio WhatsApp" if configured() else "simulated",
            "missing": [k for k in KEYS if not os.environ.get(k)]}


def normalize(phone: str | None) -> str | None:
    """Return +<country><number> or None if the input is not a plausible phone number."""
    raw = re.sub(r"[^\d+]", "", phone or "")
    if raw.startswith("00"):
        raw = "+" + raw[2:]
    if not raw.startswith("+"):
        if len(raw) == 10:
            raw = "+91" + raw
        else:
            return None
    return raw if re.fullmatch(r"\+\d{10,15}", raw) else None


def is_demo(phone: str | None) -> bool:
    n = normalize(phone)
    return n is None or n.startswith(DEMO_PREFIX)


def mask(phone: str | None) -> str:
    p = (phone or "").strip()
    return p if len(p) < 7 else p[:3] + " ••••• " + p[-3:]


def _from() -> str:
    return os.environ["TWILIO_WHATSAPP_FROM"].replace("whatsapp:", "").strip()


def send(to_phone: str, body: str) -> dict:
    """Send one WhatsApp message. Returns {ok, sid, status, error}."""
    try:
        r = httpx.post(f"{API}/{os.environ['TWILIO_ACCOUNT_SID']}/Messages.json",
                       auth=(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"]),
                       data={"From": "whatsapp:" + _from(), "To": "whatsapp:" + to_phone, "Body": body}, timeout=12)
        j = r.json()
        if r.status_code in (200, 201):
            return {"ok": True, "sid": j.get("sid"), "status": j.get("status", "queued"), "error": None}
        return {"ok": False, "sid": None, "status": "failed", "error": str(j.get("message", r.text))[:300]}
    except Exception as e:  # network, bad credentials, timeouts
        return {"ok": False, "sid": None, "status": "failed", "error": f"{type(e).__name__}: could not reach WhatsApp service"}


def fetch_status(sid: str) -> dict:
    try:
        r = httpx.get(f"{API}/{os.environ['TWILIO_ACCOUNT_SID']}/Messages/{sid}.json",
                      auth=(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"]), timeout=12)
        j = r.json()
        if r.status_code == 200:
            return {"ok": True, "status": j.get("status"), "error": j.get("error_message")}
        return {"ok": False, "status": None, "error": str(j.get("message", r.text))[:300]}
    except Exception as e:
        return {"ok": False, "status": None, "error": f"{type(e).__name__}: could not reach WhatsApp service"}
