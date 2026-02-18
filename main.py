"""
DojiSamurai ORB Webhook Server v2.0 — Alert Queue (FastAPI)
===========================================================

FIXED: Now stores ALL alerts in a queue instead of just the last one.
Bot can fetch all alerts since a given ID to ensure none are missed.

Endpoints:
  POST /webhook/orb          — Receive alert from TradingView
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

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="DojiSamurai ORB Webhook v2.0")

# Thread-safe alert storage
alerts_lock = threading.Lock()
alerts_queue: List[Dict[str, Any]] = []  # List of {id, alert, timestamp}
next_alert_id = 1
MAX_ALERTS = 100  # Keep last 100 alerts to prevent memory bloat


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
        
        # Trim old alerts if queue gets too long
        if len(alerts_queue) > MAX_ALERTS:
            alerts_queue = alerts_queue[-MAX_ALERTS:]
        
        logger.info(f"ALERT STORED → {ticker} id={alert_id} keys={list(data.keys())}")
    
    return {"status": "ok", "id": alert_id, "ticker": ticker}


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
    This is the key endpoint that prevents missed alerts.
    
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
        # Don't reset next_alert_id to avoid ID reuse issues
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
            "GET /last-alert",
            "GET /alerts-since/{id}",
            "GET /alerts-all",
            "DELETE /alerts-clear",
            "GET /health"
        ]
    }
