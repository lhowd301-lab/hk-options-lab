# -*- coding: utf-8 -*-
import requests
import time
import json
import threading
from datetime import datetime
from typing import Dict, Optional, List, Callable

class DataFeed:
    def __init__(self):
        self.running = False
        self._thread = None
        self._callbacks: List[Callable] = []
        self.latest: Dict[str, dict] = {}
    
    def on_data(self, callback: Callable):
        self._callbacks.append(callback)
    
    def start(self, codes: List[str], interval_sec: int = 30):
        self.running = True
        self._codes = codes
        self._interval = interval_sec
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True
    
    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=5)
    
    def _run(self):
        while self.running:
            try:
                for code in self._codes:
                    data = self._fetch_minute(code)
                    if data:
                        self.latest[code] = data
                        for cb in self._callbacks:
                            try:
                                cb(code, data)
                            except:
                                pass
            except:
                pass
            time.sleep(self._interval)
    
    def _fetch_minute(self, code: str) -> Optional[dict]:
        url = f"https://web.ifzq.gtimg.cn/appstock/app/minute/query?code=hk{code}"
        try:
            r = requests.get(url, timeout=10)
            data = r.json()
            hk = data["data"]["hk00700"]
            qt = hk["qt"]["hk00700"]
            min_data = hk["data"]["data"]
            last_bar = min_data[-1]
            parts = last_bar.split()
            minute = parts[0]
            price = float(parts[1])
            volume = float(parts[2])
            return {
                "code": code,
                "price": price,
                "change": float(qt[3]) - float(qt[2]) if len(qt) > 3 else 0,
                "open": float(qt[2]) if len(qt) > 2 else price,
                "high": float(qt[3]) if len(qt) > 3 else price,
                "low": float(qt[4]) if len(qt) > 4 else price,
                "volume": volume,
                "time": f"{minute[:2]}:{minute[2:]}",
                "timestamp": datetime.now().isoformat(),
                "total_volume": qt[6] if len(qt) > 6 else 0,
            }
        except:
            return None
    
    def get_futu_snapshot(self, code: str) -> Optional[dict]:
        try:
            from futu import OpenQuoteContext, RET_OK
            ctx = OpenQuoteContext(host="127.0.0.1", port=11111)
            ret, data = ctx.get_market_snapshot([f"HK.{code}"])
            ctx.close()
            if ret == RET_OK and len(data) > 0:
                row = data.iloc[0]
                return {
                    "code": code,
                    "price": float(row.get("last_price", 0)),
                    "bid": float(row.get("bid_price", 0)),
                    "ask": float(row.get("ask_price", 0)),
                    "volume": float(row.get("volume", 0)),
                    "time": datetime.now().strftime("%H:%M"),
                }
        except:
            pass
        return None
