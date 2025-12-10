from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from ib_insync import IB, Stock, StopOrder
import logging

# ================== CONFIG (CLOUD MODE – NO LOCAL TWS NEEDED) ==================
SECRET_KEY = "dojisamurai-secret-key-2025f9e8d"
IB_HOST = None          # ← we will connect from YOUR computer later
IB_PORT = None
CLIENT_ID = None
# =======================================================================

app = FastAPI()
ib = IB()
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

@app.on_event("startup")
async def startup():
    await ib.connectAsync(IB_HOST, IB_PORT, clientId=CLIENT_ID)
    logging.info("Connected to IBKR")

@app.post("/webhook/orb")
async def webhook(alert: Alert):
    if alert.key != SECRET_KEY:
        raise HTTPException(401, "Invalid key")

    entry = round(alert.orh + alert.ticks_above * 0.01, 2)
    lod = round(alert.lod, 2)
    one_r = round(entry - lod, 2)

    if (one_r / alert.atr14) * 100 > 60:
        return {"status": "rejected", "reason": "LoD distance >60%"}

    risk_usd = alert.account_equity_usd * (alert.risk_percent / 100)
    shares = int(risk_usd // one_r)
    if shares < 1:
        return {"status": "rejected", "reason": "size too small"}

    third = shares // 3
    sizes = [third, third, shares - third*2 or third]

    contract = Stock(alert.ticker, "SMART", "USD")

    parent = StopOrder("BUY", shares, entry, tif="GTC", outsideRTH=True, transmit=False)
    ib.placeOrder(contract, parent)

    stops = [
        round(entry - 0.33 * one_r, 2),
        round(entry - 0.66 * one_r, 2),
        lod
    ]

    for qty, price in zip(sizes, stops):
        child = StopOrder("SELL", qty, price, tif="GTC", outsideRTH=True, parentId=parent.orderId)
        ib.placeOrder(contract, child)

    logging.info(f"PLACED {alert.ticker} | {shares} sh | entry {entry} | stops {stops}")
    return {"status": "success", "ticker": alert.ticker, "shares": shares, "entry": entry, "stops": stops}

@app.get("/")
async def root():
    return {"message": "ORB webhook live – DojiSamurai 2025"}
