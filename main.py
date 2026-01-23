from fastapi import FastAPI, HTTPException, Request
import logging, json, re, os
from typing import Any, Dict, Optional
from pathlib import Path

app = FastAPI()
logging.basicConfig(level=logging.INFO)

SECRET_KEY = "dojisamurai-secret-key-2025f9e8d"

# Persist state to disk.
STATE_DIR = Path(os.getenv("STATE_DIR", "/tmp"))
STATE_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = STATE_DIR / "last_alert.json"


def _read_state() -> Dict[str, Any]:
    if not STATE_FILE.exists():
        return {"id": 0, "alert": None}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"id": 0, "alert": None}


def _write_state(state: Dict[str, Any]) -> None:
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    tmp.replace(STATE_FILE)


def _parse_tv_body(raw: bytes) -> Dict[str, Any]:
    s = raw.decode("utf-8", errors="replace").strip()

    # If TradingView sends invalid JSON with bare na: {"x": na}
    s = re.sub(r'(:\s*)na(\s*[,\}])', r'\1null\2', s)

    obj = json.loads(s)

    # Handle double-encoded JSON string
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
    raw = await request.body()
    try:
        data = _parse_tv_body(raw)
    except Exception as e:
        logging.error(f"422 parse fail raw={raw[:800]!r}")
        raise HTTPException(status_code=422, detail=f"Invalid JSON: {e}")

    if data.get("key") != SECRET_KEY:
        raise HTTPException(status_code=401, detail="Invalid key")

    # ═══════════════════════════════════════════════════════════════════════
    # v7.2 UPDATE: Pass through ENTIRE payload, just validate required fields
    # ═══════════════════════════════════════════════════════════════════════
    
    # Accept lod OR running_lod (backward compatible)
    if data.get("lod") is None and "running_lod" in data:
        data["lod"] = data.get("running_lod")
    
    # Validate minimum required fields exist
    ticker = data.get("ticker")
    orh = _to_float(data.get("orh"))
    lod = _to_float(data.get("lod"))
    
    # For v7.2: prefer adr/adr_pct, fall back to atr14
    adr = _to_float(data.get("adr"))
    adr_pct = _to_float(data.get("adr_pct"))
    atr14 = _to_float(data.get("atr14"))
    has_adr = (adr is not None and adr > 0) or (adr_pct is not None and adr_pct > 0) or (atr14 is not None and atr14 > 0)
    
    required_ok = (
        isinstance(ticker, str) and ticker.strip() and
        orh is not None and
        lod is not None and
        has_adr
    )

    if not required_ok:
        logging.warning(f"IGNORED alert (missing/na fields): ticker={ticker} orh={orh} lod={lod} adr={adr} atr14={atr14}")
        return {"status": "ignored", "reason": "missing_or_na_fields"}

    state = _read_state()
    new_id = int(state.get("id", 0)) + 1

    # Pass through the ENTIRE payload, just add the id
    alert_data = {**data, "id": new_id}
    
    state = {
        "id": new_id,
        "alert": alert_data
    }
    _write_state(state)

    logging.info(f"ALERT STORED → {ticker} id={new_id} keys={list(data.keys())}")
    return {"status": "stored", "id": new_id, "ticker": ticker}


@app.get("/last-alert")
async def get_last():
    return _read_state()


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "ok", "version": "v7.2"}
