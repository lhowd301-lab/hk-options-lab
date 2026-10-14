import asyncio, json, os, logging, random, sqlite3
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from contextlib import asynccontextmanager
from collections import defaultdict
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("server")

STOCK_CODES = ["HK.00700","HK.09988","HK.03690","HK.01810","HK.09618","HK.09961","HK.09888","HK.01024","HK.09999","HK.02015","HK.09866","HK.09626","HK.03888","HK.06618","HK.00020","HK.03033"]
STOCK_NAMES = {"HK.00700":"Tencent","HK.09988":"Alibaba","HK.03690":"Meituan","HK.01810":"Xiaomi","HK.09618":"JD","HK.09961":"Trip.com","HK.09888":"Baidu","HK.01024":"Kuaishou","HK.09999":"NetEase","HK.02015":"LiAuto","HK.09866":"NIO","HK.09626":"Bilibili","HK.03888":"Kingsoft","HK.06618":"JDHealth","HK.00020":"SenseTime","HK.03033":"HS Tech ETF"}
STOCK_NAMES_CN = {"HK.00700":"腾讯控股","HK.09988":"阿里巴巴","HK.03690":"美团","HK.01810":"小米集团","HK.09618":"京东集团","HK.09961":"携程集团","HK.09888":"百度集团","HK.01024":"快手","HK.09999":"网易","HK.02015":"理想汽车","HK.09866":"蔚来","HK.09626":"哔哩哔哩","HK.03888":"金山软件","HK.06618":"京东健康","HK.00020":"商汤科技","HK.03033":"恒生科技ETF"}
BASE_PRICES = {"HK.00700":380.0,"HK.09988":85.0,"HK.03690":110.0,"HK.01810":28.0,"HK.09618":120.0,"HK.09961":350.0,"HK.09888":140.0,"HK.01024":50.0,"HK.09999":150.0,"HK.02015":120.0,"HK.09866":45.0,"HK.09626":180.0,"HK.03888":35.0,"HK.06618":35.0,"HK.00020":1.5,"HK.03033":18.0}

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "platform.db")

FUTU_HOST = "127.0.0.1"
FUTU_PORT = 11111

try:
    import futu as ft
    FUTU_AVAILABLE = True
    logger.info("Futu SDK available")
except ImportError:
    FUTU_AVAILABLE = False
    logger.warning("Futu SDK not installed, using mock data")
# ===== Models =====
class StockQuote(BaseModel):
    code: str; name: str = ""; price: float = 0.0; change_pct: float = 0.0
    high_price: float = 0.0; low_price: float = 0.0; open_price: float = 0.0
    prev_close: float = 0.0; volume: int = 0; turnover: float = 0.0
    bid_price: float = 0.0; ask_price: float = 0.0; timestamp: str = ""

class Strategy(BaseModel):
    id: Optional[int] = None; name: str = ""; description: str = ""
    strategy_type: str = "custom"; stock_codes: List[str] = []
    legs: List[dict] = []; condition_code: str = ""; is_active: bool = False

class BacktestRequest(BaseModel):
    strategy_id: int; start_date: str; end_date: str
    initial_capital: float = 1000000.0; commission_rate: float = 0.0008

class BacktestResult(BaseModel):
    id: Optional[int] = None; strategy_id: int = 0; strategy_name: str = ""
    start_date: str = ""; end_date: str = ""; initial_capital: float = 0.0
    final_capital: float = 0.0; total_return: float = 0.0; annual_return: float = 0.0
    max_drawdown: float = 0.0; sharpe_ratio: float = 0.0; win_rate: float = 0.0
    total_trades: int = 0; winning_trades: int = 0; losing_trades: int = 0
    trades: list = []; equity_curve: list = []

class MonitoringRule(BaseModel):
    id: Optional[int] = None; name: str = ""; strategy_id: int = 0
    stock_codes: List[str] = []; check_interval: int = 5; is_active: bool = False

class AlertEvent(BaseModel):
    id: Optional[int] = None; rule_id: int = 0; rule_name: str = ""
    strategy_name: str = ""; stock_code: str = ""; price: float = 0.0
    signal_type: str = ""; reason: str = ""; timestamp: str = ""

# ===== Futu Data Provider =====
class FutuProvider:
    def __init__(self):
        self._ctx = None
        self._connected = False
    
    def connect(self):
        if not FUTU_AVAILABLE:
            logger.info("Futu SDK unavailable, using mock data")
            return False
        try:
            self._ctx = ft.OpenQuoteContext(host=FUTU_HOST, port=FUTU_PORT)
            self._connected = True
            logger.info("Connected to Futu OpenD")
            return True
        except Exception as e:
            logger.warning(f"Failed to connect to Futu: {e}")
            return False
    
    def disconnect(self):
        try:
            if self._ctx:
                self._ctx.close()
        except: pass
        self._connected = False
    
    def get_quotes(self, codes=None):
        if codes is None: codes = STOCK_CODES
        if self._connected:
            try:
                ret, data = self._ctx.get_market_snapshot(codes)
                if ret == 0 and data is not None and len(data) > 0:
                    results = {}
                    for _, r in data.iterrows():
                        code = str(r.get("code", ""))
                        results[code] = {
                            "code": code, "name": STOCK_NAMES_CN.get(code, STOCK_NAMES.get(code, "")),
                            "price": float(r.get("last_price", 0)), "change_pct": round((float(r.get("last_price",0))-float(r.get("prev_close_price",0)))/max(float(r.get("prev_close_price",0)),0.01)*100,2),
                            "high_price": float(r.get("high_price", 0)), "low_price": float(r.get("low_price", 0)),
                            "open_price": float(r.get("open_price", 0)), "prev_close": float(r.get("prev_close_price", 0)),
                            "volume": int(r.get("volume", 0)), "turnover": float(r.get("turnover", 0)),
                            "bid_price": float(r.get("bid_price", 0)), "ask_price": float(r.get("ask_price", 0)),
                            "timestamp": datetime.now().isoformat(),
                        }
                    return results
            except Exception as e:
                logger.warning(f"Futu fetch error: {e}")
                self._connected = False
        return self._mock_quotes(codes)
    
    def _mock_quotes(self, codes=None):
        if codes is None: codes = STOCK_CODES
        results = {}
        for c in codes:
            bp = BASE_PRICES.get(c, 100.0)
            chg = random.uniform(-3.0, 3.0)
            p = round(bp * (1 + chg/100), 2)
            results[c] = {"code":c, "name":STOCK_NAMES_CN.get(c,STOCK_NAMES.get(c,c)),
                "price":p, "change_pct":round(chg,2), "high_price":round(p*1.02,2), "low_price":round(p*0.98,2),
                "open_price":round(bp*(1+random.uniform(-1,1)/100),2), "prev_close":round(bp,2),
                "volume":random.randint(1000000,50000000), "turnover":p*random.randint(1000000,50000000),
                "timestamp":datetime.now().isoformat(), "bid_price":round(p*0.999,2), "ask_price":round(p*1.001,2)}
        return results
    
    def get_options(self, code, expiry=None):
        return self._mock_options(code, expiry)
    
    def _mock_options(self, code, expiry=None):
        bp = BASE_PRICES.get(code, 100.0)
        if not expiry: expiry = (datetime.now()+timedelta(days=30)).strftime("%Y-%m-%d")
        calls, puts = [], []
        for i in range(-5, 6):
            s = round(bp + i * bp * 0.05, 0)
            iv = random.uniform(0.2, 0.4)
            t = 30/365
            calls.append({"code":f"{code}.C{s}{expiry.replace('-','')}", "stock_code":code,
                "strike_price":s, "expiry_date":expiry, "option_type":"CALL",
                "last_price":round(max(0.01,bp-s+iv*bp*t**0.5),2), "implied_vol":round(iv,4),
                "delta":0.6, "volume":random.randint(0,1000), "open_interest":random.randint(0,5000)})
            puts.append({"code":f"{code}.P{s}{expiry.replace('-','')}", "stock_code":code,
                "strike_price":s, "expiry_date":expiry, "option_type":"PUT",
                "last_price":round(max(0.01,s-bp+iv*bp*t**0.5),2), "implied_vol":round(iv,4),
                "delta":-0.4, "volume":random.randint(0,1000), "open_interest":random.randint(0,5000)})
        return {"stock_code":code, "expiry_date":expiry, "calls":calls, "puts":puts}
    
    def save_snapshot(self, quotes):
        try:
            with sqlite3.connect(DB_PATH) as conn:
                today = datetime.now().strftime("%Y-%m-%d")
                for code, q in quotes.items():
                    sql = "INSERT OR REPLACE INTO daily_data (code, date, open_price, high_price, low_price, close_price, volume, timestamp) VALUES (?, ?, COALESCE((SELECT open_price FROM daily_data WHERE code=? AND date=?), ?), ?, ?, ?, ?, ?)"
                    conn.execute(sql, (code, today, code, today, q.get("price",0), q.get("high_price",0), q.get("low_price",0), q.get("price",0), q.get("volume",0), datetime.now().isoformat()))
        except: pass

    def get_kline(self, code, start, end):
        import pandas as pd
        dates = pd.bdate_range(start=start, end=end)
        # Try database first
        db_data = {}
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                for r in conn.execute("SELECT * FROM daily_data WHERE code=? AND date>=? AND date<=? ORDER BY date",
                    (code, start, end)):
                    db_data[r["date"]] = dict(r)
        except: pass

        real_prices = {}
        if self._connected:
            try:
                r, d = self._ctx.get_market_snapshot([code])
                if r == 0 and d is not None and len(d) > 0:
                    real_prices[code] = float(d.iloc[0].get("last_price", 0))
            except: pass

        bp = real_prices.get(code, BASE_PRICES.get(code, 100.0))
        p = bp
        data = []
        for d in dates:
            ds = d.strftime("%Y-%m-%d")
            if ds in db_data:
                dd = db_data[ds]
                data.append({"code":code, "time_key":ds,
                    "open":dd.get("open_price",0), "high":dd.get("high_price",0),
                    "low":dd.get("low_price",0), "close":dd.get("close_price",0),
                    "volume":dd.get("volume",0), "source":"real"})
                p = dd.get("close_price", p)
            else:
                daily_vol = random.uniform(0.005, 0.025)
                trend = random.gauss(0, 0.001)
                change = trend + random.gauss(0, daily_vol)
                p = max(0.1, round(p * (1 + change), 2))
                o = round(p * (1 + random.uniform(-0.003, 0.003)), 2)
                h = round(max(p, o) * (1 + random.uniform(0, 0.005)), 2)
                l = round(min(p, o) * (1 - random.uniform(0, 0.005)), 2)
                data.append({"code":code, "time_key":ds,
                    "open":o, "high":h, "low":l, "close":p,
                    "volume":random.randint(500000,10000000), "source":"simulated"})
        return data

provider = FutuProvider()

# ===== Database =====
def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS strategies (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, description TEXT DEFAULT '', strategy_type TEXT DEFAULT 'custom', stock_codes TEXT DEFAULT '[]', legs TEXT DEFAULT '[]', condition_code TEXT DEFAULT '', is_active INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime('now','localtime')), updated_at TEXT DEFAULT (datetime('now','localtime')));
            CREATE TABLE IF NOT EXISTS backtest_results (id INTEGER PRIMARY KEY AUTOINCREMENT, strategy_id INTEGER NOT NULL, strategy_name TEXT DEFAULT '', start_date TEXT NOT NULL, end_date TEXT NOT NULL, initial_capital REAL DEFAULT 0.0, final_capital REAL DEFAULT 0.0, total_return REAL DEFAULT 0.0, annual_return REAL DEFAULT 0.0, max_drawdown REAL DEFAULT 0.0, sharpe_ratio REAL DEFAULT 0.0, win_rate REAL DEFAULT 0.0, total_trades INTEGER DEFAULT 0, winning_trades INTEGER DEFAULT 0, losing_trades INTEGER DEFAULT 0, trades TEXT DEFAULT '[]', equity_curve TEXT DEFAULT '[]', created_at TEXT DEFAULT (datetime('now','localtime')));
            CREATE TABLE IF NOT EXISTS monitoring_rules (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, strategy_id INTEGER NOT NULL, stock_codes TEXT DEFAULT '[]', check_interval INTEGER DEFAULT 5, is_active INTEGER DEFAULT 0, notification_type TEXT DEFAULT 'LOG');
            CREATE TABLE IF NOT EXISTS strategy_signals (id INTEGER PRIMARY KEY AUTOINCREMENT, strategy_id INTEGER NOT NULL, strategy_name TEXT DEFAULT '', signal_type TEXT NOT NULL, stock_code TEXT NOT NULL, price REAL DEFAULT 0.0, reason TEXT DEFAULT '', legs TEXT DEFAULT '[]', timestamp TEXT DEFAULT (datetime('now','localtime')), executed INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS daily_data (
    code TEXT, date TEXT, open_price REAL DEFAULT 0, high_price REAL DEFAULT 0,
    low_price REAL DEFAULT 0, close_price REAL DEFAULT 0, volume INTEGER DEFAULT 0,
    timestamp TEXT, PRIMARY KEY (code, date));
            CREATE TABLE IF NOT EXISTS alert_events (id INTEGER PRIMARY KEY AUTOINCREMENT, rule_id INTEGER NOT NULL, rule_name TEXT DEFAULT '', strategy_name TEXT DEFAULT '', stock_code TEXT DEFAULT '', stock_name TEXT DEFAULT '', price REAL DEFAULT 0.0, signal_type TEXT DEFAULT '', reason TEXT DEFAULT '', timestamp TEXT DEFAULT (datetime('now','localtime')), acknowledged INTEGER DEFAULT 0);
        """)

# ===== Strategy Engine =====
class StrategyEngine:
    def evaluate(self, strategy, quotes):
        if strategy.condition_code:
            try:
                l = {"quotes":quotes, "stock_codes":strategy.stock_codes, "trigger":False, "reason":"", "price":0.0, "stock_code":""}
                exec(strategy.condition_code, {"__builtins__": __builtins__}, l)
                if l["trigger"]:
                    return {"type":"ENTRY", "stock_code":l.get("stock_code",""), "price":l.get("price",0), "reason":l.get("reason","")}
            except Exception as e:
                logger.warning(f"Eval error: {e}")
        return None
    def identify(self, name, desc, code, legs):
        text = f"{name} {desc} {code}".lower()
        if "covered" in text or "备兑" in text: return "covered_call"
        if "straddle" in text or "跨式" in text: return "straddle"
        if "conversion" in text or "转换" in text: return "conversion"
        if "strangle" in text or "宽跨" in text: return "strangle"
        if "box" in text or "盒式" in text: return "box_spread"
        return "custom"

strategy_engine = StrategyEngine()

# ===== Backtest Engine =====
class BacktestEngine:
    def run(self, strategy, request, historical):
        capital = request.initial_capital
        trades = []; curve = []; positions = {}
        all_dates = sorted(set(
            k["time_key"] for code in strategy.stock_codes
            for k in historical.get(code, [])
            if request.start_date <= k["time_key"] <= request.end_date
        ))
        if not all_dates:
            return BacktestResult(strategy_id=strategy.id, strategy_name=strategy.name,
                start_date=request.start_date, end_date=request.end_date,
                initial_capital=request.initial_capital, final_capital=request.initial_capital,
                total_return=0, annual_return=0, max_drawdown=0, sharpe_ratio=0, win_rate=0,
                total_trades=0, winning_trades=0, losing_trades=0)

        for date in all_dates:
            quotes = {}
            for code in strategy.stock_codes:
                for k in historical.get(code, []):
                    if k["time_key"] == date:
                        quotes[code] = k; break

            signal = None
            if strategy.condition_code:
                try:
                    l = {"quotes":quotes, "stock_codes":strategy.stock_codes,
                         "trigger":False, "reason":"", "price":0.0, "stock_code":"",
                         "signal_type":"ENTRY", "date":date}
                    exec(strategy.condition_code, {"__builtins__":__builtins__}, l)
                    if l.get("trigger"):
                        signal = {"type":l.get("signal_type","ENTRY"),
                                  "stock_code":l.get("stock_code",""),
                                  "price":l.get("price",0), "reason":l.get("reason","")}
                except: pass

            if signal:
                code = signal["stock_code"] or (strategy.stock_codes[0] if strategy.stock_codes else "")
                price = signal["price"] or quotes.get(code,{}).get("close",0)
                if not code or price <= 0: continue

                if signal["type"] == "ENTRY":
                    qty = max(100, int(capital * 0.2 / price) // 100 * 100)
                    cost = price * qty * (1 + request.commission_rate)
                    if capital >= cost and qty > 0:
                        capital -= cost
                        positions[code] = positions.get(code,0) + qty
                        trades.append({"date":date, "stock_code":code, "action":"ENTRY",
                            "price":round(price,2), "quantity":qty,
                            "commission":round(price*qty*request.commission_rate,2)})
                elif signal["type"] == "EXIT" and code in positions and positions[code] > 0:
                    qty = positions[code]
                    revenue = price * qty * (1 - request.commission_rate)
                    capital += revenue
                    trades.append({"date":date, "stock_code":code, "action":"EXIT",
                        "price":round(price,2), "quantity":qty,
                        "commission":round(price*qty*request.commission_rate,2)})
                    positions[code] = 0

            pos_value = sum(quotes.get(c,{}).get("close",0) * q for c,q in positions.items() if q > 0)
            curve.append({"date":date, "equity":round(capital + pos_value,2)})

        for code in list(positions.keys()):
            if positions.get(code,0) > 0 and all_dates:
                last = all_dates[-1]
                for k in historical.get(code,[]):
                    if k["time_key"] == last:
                        capital += k["close"] * positions[code] * (1 - request.commission_rate)
                        break

        initial = request.initial_capital
        final = curve[-1]["equity"] if curve else initial
        tr = (final - initial) / initial * 100
        equities = [e["equity"] for e in curve]
        peak = initial; max_dd = 0
        for eq in equities:
            if eq > peak: peak = eq
            dd = (peak - eq) / peak * 100
            max_dd = max(max_dd, dd)

        start_dt = datetime.strptime(request.start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(request.end_date, "%Y-%m-%d")
        days = max(1, (end_dt - start_dt).days)
        annual = ((1 + tr/100) ** (365/days) - 1) * 100 if days > 0 else 0

        winning = sum(1 for t in trades if t.get("pnl",0) > 0)
        losing = len(trades) - winning
        win_rate = (winning / len(trades) * 100) if trades else 0

        if len(equities) > 1:
            import numpy as np
            returns = np.diff(equities) / np.array(equities[:-1])
            rf = 0.02 / 252
            ex = returns - rf
            sharpe = round(np.mean(ex) / max(np.std(ex),1e-10) * np.sqrt(252), 2) if len(ex) > 0 else 0
        else:
            sharpe = 0

        return BacktestResult(
            strategy_id=strategy.id, strategy_name=strategy.name,
            start_date=request.start_date, end_date=request.end_date,
            initial_capital=initial, final_capital=round(final,2),
            total_return=round(tr,2), annual_return=round(annual,2),
            max_drawdown=round(max_dd,2), sharpe_ratio=sharpe,
            win_rate=round(win_rate,2), total_trades=len(trades),
            winning_trades=winning, losing_trades=losing,
            trades=trades, equity_curve=curve)

backtest_engine = BacktestEngine()

# ===== WebSocket Manager =====
class ConnectionManager:
    def __init__(self):
        self.active = []
    async def connect(self, ws):
        await ws.accept(); self.active.append(ws)
    def disconnect(self, ws):
        if ws in self.active: self.active.remove(ws)
    async def broadcast(self, msg):
        dead = []
        for ws in self.active:
            try: await ws.send_json(msg)
            except: dead.append(ws)
        for ws in dead: self.disconnect(ws)

ws_manager = ConnectionManager()

# ===== Background Quote Pusher =====
class QuotePusher:
    def __init__(self):
        self._task = None; self._running = False
    
    async def start(self):
        if self._running: return
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("Quote pusher started (2s interval)")
    
    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try: await self._task
            except: pass
            self._task = None
    
    async def _run(self):
        connected = provider.connect()
        while self._running:
            try:
                quotes = provider.get_quotes()
                if quotes:
                    provider.save_snapshot(quotes)
                    await ws_manager.broadcast({
                        "type": "quote",
                        "data": quotes,
                        "timestamp": datetime.now().isoformat(),
                    })
            except Exception as e:
                logger.warning(f"Quote push error: {e}")
            await asyncio.sleep(2)

quote_pusher = QuotePusher()

# ===== FastAPI App =====
@asynccontextmanager
async def lifespan(app):
    init_db()
    logger.info("Quote pusher ready")
    yield
    await quote_pusher.stop()
    provider.disconnect()

app = FastAPI(title="Options Platform", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/api/health")
async def health():
    return {"status":"ok", "futu_connected":provider._connected, "pusher_running":quote_pusher._running, "timestamp":datetime.now().isoformat()}

@app.get("/api/quotes")
async def get_quotes():
    return {"quotes": provider.get_quotes()}

@app.get("/api/quotes/{code}")
async def get_quote(code: str):
    if not code.startswith("HK."): code = "HK." + code
    q = provider.get_quotes([code])
    if code not in q: raise HTTPException(404)
    return q[code]

@app.get("/api/options/{code}")
async def get_options(code: str, expiry: str = None):
    if not code.startswith("HK."): code = "HK." + code
    return provider.get_options(code, expiry)

@app.get("/api/monitor/status")
async def monitor_status():
    return {"running":quote_pusher._running, "futu_connected":provider._connected, "futu_available":FUTU_AVAILABLE, "ws_clients":len(ws_manager.active)}

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            t = msg.get("type","")
            if t in ("refresh_quotes", "subscribe_quotes"):
                codes = msg.get("codes") if t == "subscribe_quotes" else None
                q = provider.get_quotes(codes)
                await ws.send_json({"type":"quote", "data":q, "timestamp":datetime.now().isoformat()})
            elif t == "ping":
                await ws.send_json({"type":"pong"})
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)
    except Exception as e:
        logger.warning(f"WS error: {e}")
        ws_manager.disconnect(ws)

# ===== Strategy CRUD =====
@app.get("/api/strategies")
async def list_strategies():
    results = []
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            for r in conn.execute("SELECT * FROM strategies ORDER BY id DESC"):
                d = dict(r)
                d["stock_codes"] = json.loads(d.get("stock_codes","[]"))
                d["legs"] = json.loads(d.get("legs","[]"))
                results.append(d)
    except: pass
    return {"strategies": results}

@app.post("/api/strategies")
async def create_strategy(s: Strategy):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("INSERT INTO strategies (name,description,strategy_type,stock_codes,legs,condition_code,is_active) VALUES (?,?,?,?,?,?,?)",
            (s.name, s.description, s.strategy_type, json.dumps(s.stock_codes), json.dumps(s.legs), s.condition_code, 1 if s.is_active else 0))
        return {"id": cur.lastrowid}

@app.get("/api/strategies/{sid}")
async def get_strategy(sid: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM strategies WHERE id=?", (sid,)).fetchone()
        if not row: raise HTTPException(404)
        d = dict(row)
        d["stock_codes"] = json.loads(d["stock_codes"])
        d["legs"] = json.loads(d["legs"])
        return {"strategy": d}

@app.put("/api/strategies/{sid}")
async def update_strategy(sid: int, s: Strategy):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE strategies SET name=?,description=?,strategy_type=?,stock_codes=?,legs=?,condition_code=?,is_active=?,updated_at=datetime('now','localtime') WHERE id=?",
            (s.name, s.description, s.strategy_type, json.dumps(s.stock_codes), json.dumps(s.legs), s.condition_code, 1 if s.is_active else 0, sid))
        return {"status":"ok"}

@app.delete("/api/strategies/{sid}")
async def delete_strategy(sid: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM strategies WHERE id=?", (sid,))
    return {"status":"deleted"}

@app.post("/api/strategies/identify")
async def identify(data: dict):
    stype = strategy_engine.identify(data.get("name",""), data.get("description",""), data.get("code",""), data.get("legs",[]))
    return {"strategy_type": stype}

# ===== Backtest =====
@app.post("/api/backtest")
async def run_backtest(req: BacktestRequest):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM strategies WHERE id=?", (req.strategy_id,)).fetchone()
        if not row: raise HTTPException(404, "Strategy not found")
        d = dict(row)
        d["stock_codes"] = json.loads(d["stock_codes"])
        d["legs"] = json.loads(d["legs"])
        s = Strategy(**d)
    historical = {}
    for code in s.stock_codes:
        historical[code] = provider.get_kline(code, req.start_date, req.end_date)
    result = backtest_engine.run(s, req, historical)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO backtest_results (strategy_id,strategy_name,start_date,end_date,initial_capital,final_capital,total_return,annual_return,max_drawdown,sharpe_ratio,win_rate,total_trades,winning_trades,losing_trades,trades,equity_curve) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (result.strategy_id, result.strategy_name, result.start_date, result.end_date, result.initial_capital, result.final_capital, result.total_return, result.annual_return, result.max_drawdown, result.sharpe_ratio, result.win_rate, result.total_trades, result.winning_trades, result.losing_trades, json.dumps(result.trades), json.dumps(result.equity_curve)))
    return {"result": result.dict()}

@app.get("/api/backtest/results")
async def list_backtest_results(strategy_id: int = None):
    results = []
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            q = "SELECT * FROM backtest_results"
            p = []
            if strategy_id:
                q += " WHERE strategy_id=?"
                p.append(strategy_id)
            q += " ORDER BY id DESC LIMIT 50"
            for r in conn.execute(q, p):
                d = dict(r)
                d["trades"] = json.loads(d.get("trades","[]"))
                d["equity_curve"] = json.loads(d.get("equity_curve","[]"))
                results.append(d)
    except: pass
    return {"results": results}


@app.delete("/api/backtest/results/{rid}")
async def delete_backtest_result(rid: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM backtest_results WHERE id=?", (rid,))
    return {"status":"deleted"}
# ===== Monitor & Alerts =====
@app.get("/api/alerts")
async def get_alerts():
    alerts = []
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            for r in conn.execute("SELECT * FROM alert_events ORDER BY timestamp DESC LIMIT 100"):
                alerts.append(dict(r))
    except: pass
    return {"alerts": alerts}

@app.get("/api/signals")
async def get_signals(strategy_id: int = None):
    sigs = []
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            q = "SELECT * FROM strategy_signals"
            p = []
            if strategy_id:
                q += " WHERE strategy_id=?"
                p.append(strategy_id)
            q += " ORDER BY timestamp DESC LIMIT 100"
            for r in conn.execute(q, p):
                d = dict(r)
                d["legs"] = json.loads(d.get("legs","[]"))
                sigs.append(d)
    except: pass
    return {"signals": sigs}

@app.get("/api/data/refresh")
async def refresh_data():
    return {"quotes": provider.get_quotes()}

# ===== Serve Frontend =====
frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
