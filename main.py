from fastapi import FastAPI, Request, HTTPException
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
    account_equity_usd: float = 101428
    risk_percent: float = 0.25
    key: str

SECRET_KEY = "dojisamurai-secret-key-2025f9e8d"

@app.get("/")
async def root():
    return {"message": "ORB webhook live – DojiSamurai 2025 – cloud mode"}

@app.post("/webhook/orb")
async def webhook(alert: Alert):
    if alert.key != SECRET_KEY:
        raise HTTPException(401, "Bad key")

    logging.info(f"Received valid alert for {alert.ticker}")
    return {
        "status": "received",
        "ticker": alert.ticker,
        "entry": round(alert.orh + alert.ticks_above * 0.01, 2),
        "lod": alert.lod,
        "1R": round(alert.orh + alert.ticks_above * 0.01 - alert.lod, 2)
    }
