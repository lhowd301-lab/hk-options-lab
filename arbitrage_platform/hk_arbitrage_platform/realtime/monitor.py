# -*- coding: utf-8 -*-
import time
import json
from datetime import datetime
from typing import Dict, List, Optional
from ..backtest.strategies import RSIMeanReversion, VolatilityBreakout
import numpy as np
import pandas as pd

STRATEGIES = {
    "rsi_mean_reversion": RSIMeanReversion,
    "volatility_breakout": VolatilityBreakout,
}

class Monitor:
    def __init__(self, datafeed):
        self.datafeed = datafeed
        self.signal_log: List[dict] = []
        self.running = False
        self.strategy_name = "rsi_mean_reversion"
        self.price_history: Dict[str, List[float]] = {}
        self.last_rsi: Dict[str, float] = {}
        
        datafeed.on_data(self._on_data)
    
    def start(self):
        self.running = True
        self.datafeed.start(self._codes, self._interval)
    
    def stop(self):
        self.running = False
        self.datafeed.stop()
    
    def configure(self, codes: List[str], strategy: str = "rsi_mean_reversion", interval: int = 30):
        self._codes = codes
        self.strategy_name = strategy
        self._interval = interval
        for code in codes:
            if code not in self.price_history:
                self.price_history[code] = []
    
    def _on_data(self, code: str, data: dict):
        if not self.running:
            return
        price = data["price"]
        self.price_history.setdefault(code, []).append(price)
        keep = 50
        if len(self.price_history[code]) > keep:
            self.price_history[code] = self.price_history[code][-keep:]
        
        # Run strategy
        signal = self._evaluate(code)
        if signal:
            signal["timestamp"] = datetime.now().isoformat()
            signal["price"] = price
            signal["price_time"] = data["time"]
            self.signal_log.append(signal)
            if len(self.signal_log) > 100:
                self.signal_log = self.signal_log[-100:]
    
    def _evaluate(self, code: str) -> Optional[dict]:
        prices = self.price_history.get(code, [])
        if len(prices) < 16:
            return None
        
        arr = np.array(prices)
        delta = np.diff(arr)
        g = np.where(delta > 0, delta, 0)
        l = np.where(delta < 0, -delta, 0)
        ag = np.mean(g[-14:])
        al = max(np.mean(l[-14:]), 0.001)
        rsi = 100 - 100 / (1 + ag / al)
        self.last_rsi[code] = round(rsi, 1)
        
        curr = prices[-1]
        if self.strategy_name == "rsi_mean_reversion":
            if rsi < 30:
                return {"code": code, "strategy": "RSI Mean Reversion", "action": "BUY CALL",
                        "entry": round(curr, 2), "stop": round(curr * 0.97, 2),
                        "target": round(curr * 1.03, 2), "rsi": round(rsi, 1), "reason": "RSI oversold"}
            elif rsi > 70:
                return {"code": code, "strategy": "RSI Mean Reversion", "action": "BUY PUT",
                        "entry": round(curr, 2), "stop": round(curr * 1.03, 2),
                        "target": round(curr * 0.97, 2), "rsi": round(rsi, 1), "reason": "RSI overbought"}
        
        elif self.strategy_name == "volatility_breakout":
            if len(prices) >= 20:
                high20 = max(prices[-20:])
                low20 = min(prices[-20:])
                bp = 0.002
                if curr > high20 * (1 + bp):
                    return {"code": code, "strategy": "VolBreakout", "action": "BUY CALL",
                            "entry": round(curr, 2), "stop": round(high20, 2),
                            "target": round(curr * 1.05, 2), "reason": "Breakout above 20d high"}
                elif curr < low20 * (1 - bp):
                    return {"code": code, "strategy": "VolBreakout", "action": "BUY PUT",
                            "entry": round(curr, 2), "stop": round(low20, 2),
                            "target": round(curr * 0.95, 2), "reason": "Breakout below 20d low"}
        
        return None
    
    def get_state(self) -> dict:
        prices = {}
        for code in self.datafeed.latest:
            d = self.datafeed.latest[code]
            prices[code] = {
                "price": d.get("price"),
                "change": d.get("change"),
                "volume": d.get("volume"),
                "time": d.get("time"),
            }
            if code in self.last_rsi:
                prices[code]["rsi"] = self.last_rsi[code]
        return {
            "running": self.running,
            "strategy": self.strategy_name,
            "prices": prices,
            "signals": self.signal_log[-20:] if self.signal_log else [],
            "signal_count": len(self.signal_log),
        }
