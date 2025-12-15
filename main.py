from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import logging

app = FastAPI()
logging.basicConfig(level=logging.INFO)

class Alert(BaseModel):
    ticker: str
    orh: float
    lod: float
    atr14: float
    ticks_above: int = 3
    account_equity_usd: float = 350000
    risk_percent: float = 0.25
    key: str

SECRET_KEY = "dojisamurai-secret-key-2025f9e8d"

# Storage for polling
last_alert = None
last_id = 0

@app.get("/")
async def root():
    return {"message": "ORB webhook live – DojiSamurai 2025"}

@app.post("/webhook/orb")
async def webhook(alert: Alert):
    global last_alert, last_id
    if alert.key != SECRET_KEY:
        raise HTTPException(status_code=401, detail="Invalid key")
    last_id += 1
    last_alert = alert.dict()
    last_alert["id"] = last_id
    logging.info(f"ALERT STORED → {alert.ticker}")
    return {"status": "stored", "id": last_id, "ticker": alert.ticker}

@app.get("/last-alert")
async def get_last():
    if last_alert:
        return {"id": last_id, "alert": last_alert}
    return {"id": 0, "alert": None}
