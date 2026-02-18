"""
DojiSamurai ORB Webhook Server v2.0 — Alert Queue
==================================================

FIXED: Now stores ALL alerts in a queue instead of just the last one.
Bot can fetch all alerts since a given ID to ensure none are missed.

Endpoints:
  POST /webhook/orb          — Receive alert from TradingView
  GET  /last-alert           — Get most recent alert (backwards compatible)
  GET  /alerts-since/<id>    — Get ALL alerts since given ID (new)
  GET  /alerts-all           — Get all stored alerts (debug)
  GET  /health               — Health check
  DELETE /alerts-clear       — Clear all alerts (admin)

Deploy to Render as a Python web service.
"""

from flask import Flask, request, jsonify
import threading
import time
import os

app = Flask(__name__)

# Thread-safe alert storage
alerts_lock = threading.Lock()
alerts_queue = []  # List of {id, alert, timestamp}
next_alert_id = 1
MAX_ALERTS = 100  # Keep last 100 alerts to prevent memory bloat

def get_next_id():
    global next_alert_id
    aid = next_alert_id
    next_alert_id += 1
    return aid

@app.route("/webhook/orb", methods=["POST"])
def receive_alert():
    """Receive alert from TradingView and add to queue."""
    global alerts_queue
    
    try:
        data = request.get_json(force=True)
    except Exception as e:
        app.logger.error(f"JSON parse error: {e}")
        return jsonify({"error": "Invalid JSON"}), 400
    
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
        
        app.logger.info(f"ALERT STORED → {ticker} id={alert_id} keys={list(data.keys())}")
    
    return jsonify({"status": "ok", "id": alert_id, "ticker": ticker}), 200


@app.route("/last-alert", methods=["GET"])
def last_alert():
    """Get most recent alert (backwards compatible with existing bot)."""
    with alerts_lock:
        if not alerts_queue:
            return jsonify({"id": None, "alert": None}), 200
        
        latest = alerts_queue[-1]
        return jsonify({"id": latest["id"], "alert": latest["alert"]}), 200


@app.route("/alerts-since/<int:since_id>", methods=["GET"])
def alerts_since(since_id):
    """
    Get ALL alerts with ID > since_id.
    This is the key endpoint that prevents missed alerts.
    
    Returns: {"alerts": [{id, alert}, ...], "count": N}
    """
    with alerts_lock:
        newer = [{"id": a["id"], "alert": a["alert"]} 
                 for a in alerts_queue if a["id"] > since_id]
        return jsonify({"alerts": newer, "count": len(newer)}), 200


@app.route("/alerts-all", methods=["GET"])
def alerts_all():
    """Debug endpoint to see all stored alerts."""
    with alerts_lock:
        return jsonify({
            "alerts": [{"id": a["id"], "ticker": a["alert"].get("ticker", "?")} 
                      for a in alerts_queue],
            "count": len(alerts_queue),
            "next_id": next_alert_id
        }), 200


@app.route("/alerts-clear", methods=["DELETE"])
def alerts_clear():
    """Admin endpoint to clear all alerts."""
    global alerts_queue, next_alert_id
    with alerts_lock:
        count = len(alerts_queue)
        alerts_queue = []
        # Don't reset next_alert_id to avoid ID reuse issues
        return jsonify({"status": "cleared", "removed": count}), 200


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    with alerts_lock:
        return jsonify({
            "status": "ok",
            "alerts_queued": len(alerts_queue),
            "next_id": next_alert_id
        }), 200


# Render uses PORT env var
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
