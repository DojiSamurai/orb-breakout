"""
DojiSamurai ORB Webhook Server v2.0 — Alert Queue (FastAPI)
===========================================================

FIXED: Now stores ALL alerts in a queue instead of just the last one.
Bot can fetch all alerts since a given ID to ensure none are missed.

Endpoints:
  POST /webhook/orb          — Receive alert from TradingView
  POST /webhook/regime       — Receive regime alert from TradingView, forward to bot
  GET  /last-alert           — Get most recent alert (backwards compatible)
  GET  /alerts-since/{id}    — Get ALL alerts since given ID (new)
  GET  /alerts-all           — Get all stored alerts (debug)
  DELETE /alerts-clear       — Clear all alerts (admin)
  GET  /health               — Health check

Deploy to Render as a Python web service.
Start command: uvicorn main:app --host 0.0.0.0 --port $PORT
"""

from fastapi import FastAPI, Request
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
import threading
import time
import logging
import httpx

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="DojiSamurai ORB Webhook v2.0")

# VPS bot address
VPS_IP = "5.161.96.166"

# Thread-safe alert storage
alerts_lock = threading.Lock()
alerts_queue: List[Dict[str, Any]] = []
next_alert_id = 1
MAX_ALERTS = 100


def get_next_id() -> int:
    global next_alert_id
    aid = next_alert_id
    next_alert_id += 1
    return aid


@app.post("/webhook/orb")
async def receive_alert(request: Request):
    """Receive alert from TradingView and add to queue."""
    global alerts_queue

    try:
        data = await request.json()
    except Exception as e:
        logger.error(f"JSON parse error: {e}")
        return {"error": "Invalid JSON"}

    ticker = data.get("ticker", "UNKNOWN")

    with alerts_lock:
        alert_id = get_next_id()
        alert_entry = {
            "id": alert_id,
            "alert": data,
            "timestamp": time.time()
        }
        alerts_queue.append(alert_entry)

        if len(alerts_queue) > MAX_ALERTS:
            alerts_queue = alerts_queue[-MAX_ALERTS:]

        logger.info(f"ALERT STORED → {ticker} id={alert_id} keys={list(data.keys())}")

    return {"status": "ok", "id": alert_id, "ticker": ticker}


@app.post("/webhook/regime")
async def receive_regime(request: Request):
    """Receive regime alert from TradingView Pine and forward to bot."""
    try:
        data = await request.json()
    except Exception as e:
        logger.error(f"Regime JSON parse error: {e}")
        return {"error": "Invalid JSON"}

    ticker = data.get("symbol", data.get("ticker", "SPY"))
    regime = data.get("regime", "UNKNOWN")
    logger.info(f"REGIME ALERT → {ticker} regime={regime}")

    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"http://{VPS_IP}:8089/webhook/regime",
                json=data,
                timeout=5.0
            )
        logger.info(f"REGIME forwarded to bot OK")
    except Exception as e:
        logger.warning(f"Failed to forward regime to bot: {e}")

    return {"status": "ok", "ticker": ticker, "regime": regime}


@app.get("/last-alert")
async def last_alert():
    """Get most recent alert (backwards compatible with existing bot)."""
    with alerts_lock:
        if not alerts_queue:
            return {"id": None, "alert": None}

        latest = alerts_queue[-1]
        return {"id": latest["id"], "alert": latest["alert"]}


@app.get("/alerts-since/{since_id}")
async def alerts_since(since_id: int):
    """
    Get ALL alerts with ID > since_id.
    Returns: {"alerts": [{id, alert}, ...], "count": N}
    """
    with alerts_lock:
        newer = [{"id": a["id"], "alert": a["alert"]}
                 for a in alerts_queue if a["id"] > since_id]
        return {"alerts": newer, "count": len(newer)}


@app.get("/alerts-all")
async def alerts_all():
    """Debug endpoint to see all stored alerts."""
    with alerts_lock:
        return {
            "alerts": [{"id": a["id"], "ticker": a["alert"].get("ticker", "?")}
                       for a in alerts_queue],
            "count": len(alerts_queue),
            "next_id": next_alert_id
        }


@app.delete("/alerts-clear")
async def alerts_clear():
    """Admin endpoint to clear all alerts."""
    global alerts_queue
    with alerts_lock:
        count = len(alerts_queue)
        alerts_queue = []
        return {"status": "cleared", "removed": count}


@app.get("/health")
async def health():
    """Health check endpoint."""
    with alerts_lock:
        return {
            "status": "ok",
            "alerts_queued": len(alerts_queue),
            "next_id": next_alert_id
        }


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "DojiSamurai ORB Webhook v2.0",
        "endpoints": [
            "POST /webhook/orb",
            "POST /webhook/regime",
            "GET /last-alert",
            "GET /alerts-since/{id}",
            "GET /alerts-all",
            "DELETE /alerts-clear",
            "GET /health"
        ]
    }
