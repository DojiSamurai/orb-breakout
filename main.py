from fastapi import FastAPI, HTTPException, Request
import logging, json, re
from typing import Any, Dict, Optional

app = FastAPI()
logging.basicConfig(level=logging.INFO)

SECRET_KEY = "dojisamurai-secret-key-2025f9e8d"

last_alert: Optional[Dict[str, Any]] = None
last_id: int = 0


def _parse_tv_body(raw: bytes) -> Dict[str, Any]:
    s = raw.decode("utf-8", errors="replace").strip()

    # If TradingView ever sends invalid JSON with bare na (unquoted), fix it:
    s = re.sub(r'(:\s*)na(\s*[,\}])', r'\1null\2', s)

    obj = json.loads(s)

    # Handle rare case of double-encoded JSON string
    if isinstance(obj, str):
        obj = json.loads(obj)

    if not isinstance(obj, dict):
        raise ValueError("Payload is not a JSON object")
    return obj


def _to_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        t = v.strip().lower()
        if t in ("na", "null", ""):
            return None
        return float(t)
    return None


def _to_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str):
        t = v.strip().lower()
        if t in ("na", "null", ""):
            return None
        return int(float(t))
    return None


@app.get("/")
async def root():
    return {"message": "ORB webhook live – DojiSamurai 2025"}


@app.post("/webhook/orb")
async def webhook(request: Request):
    global last_alert, last_id

    raw = await request.body()
    try:
        data = _parse_tv_body(raw)
    except Exception as e:
        logging.error(f"422 parse fail. raw={raw[:500]!r}")
        raise HTTPException(status_code=422, detail=f"Invalid JSON: {e}")

    if data.get("key") != SECRET_KEY:
        raise HTTPException(status_code=401, detail="Invalid key")

    # Normalize fields
    normalized = {
        "ticker": data.get("ticker"),
        "tf": data.get("tf"),
        "orh": _to_float(data.get("orh")),
        "trigger": _to_float(data.get("trigger")),
        "lod": _to_float(data.get("running_lod")),          # <- map to lod
        "running_lod": _to_float(data.get("running_lod")),
        "atr14": _to_float(data.get("atr14")),
        "lodPct_orh": _to_float(data.get("lodPct_orh")),
        "rvol_orh": _to_float(data.get("rvol_orh")),
        "ticks_above": _to_int(data.get("ticks_above")),
        "key": data.get("key"),
    }

    # Minimum required sanity checks
    if not normalized["ticker"]:
        raise HTTPException(status_code=422, detail="Missing ticker")
    if normalized["orh"] is None or normalized["lod"] is None:
        # You can choose to store anyway, but don't trade on it
        logging.warning(f"Alert missing numeric fields: {normalized}")

    last_id += 1
    normalized["id"] = last_id
    last_alert = normalized

    logging.info(f"ALERT STORED → {normalized['ticker']} id={last_id}")
    return {"status": "stored", "id": last_id, "ticker": normalized["ticker"]}


@app.get("/last-alert")
async def get_last():
    return {"id": last_id, "alert": last_alert}
