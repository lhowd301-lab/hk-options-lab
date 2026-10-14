# -*- coding: utf-8 -*-
from datetime import datetime
from typing import Dict, List, Optional
import time

class Executor:
    def __init__(self, monitor=None):
        self.monitor = monitor
        self.auto_trade = False
        self.positions: Dict[str, dict] = {}
        self.trade_log: List[dict] = []
        self.capital = 100000.0
        self._pending_signals: List[dict] = []
    
    def set_auto_trade(self, enabled: bool):
        self.auto_trade = enabled
    
    def on_signal(self, signal: dict):
        self._pending_signals.append(signal)
        if self.auto_trade:
            self._execute(signal)
    
    def _execute(self, signal: dict):
        code = signal["code"]
        action = signal["action"]
        entry = signal["entry"]
        
        # Check if already in position
        if code in self.positions:
            return
        
        quantity = int(self.capital * 0.02 / entry)  # 2% risk per trade
        if quantity < 1:
            quantity = 1
        
        position = {
            "code": code,
            "action": action,
            "entry": entry,
            "quantity": quantity,
            "stop": signal.get("stop", entry * 0.97),
            "target": signal.get("target", entry * 1.03),
            "entry_time": datetime.now().isoformat(),
            "pnl": 0.0,
            "status": "open",
        }
        
        self.positions[code] = position
        self.capital -= entry * quantity * 0.1  # margin ~10%
        
        trade = {
            "time": datetime.now().isoformat(),
            "code": code,
            "action": action,
            "entry": entry,
            "quantity": quantity,
            "type": "auto" if self.auto_trade else "manual",
        }
        self.trade_log.append(trade)
        if len(self.trade_log) > 100:
            self.trade_log = self.trade_log[-100:]
    
    def close_position(self, code: str, price: float):
        if code not in self.positions:
            return
        pos = self.positions[code]
        if pos["action"].startswith("BUY CALL") or pos["action"].startswith("BUY PUT"):
            pnl = (price - pos["entry"]) * pos["quantity"]
        else:
            pnl = (pos["entry"] - price) * pos["quantity"]
        
        # Simulate option leverage
        pnl = pnl * 0.5  # 50% of underlying move
        
        pos["pnl"] = round(pnl, 2)
        pos["exit"] = price
        pos["exit_time"] = datetime.now().isoformat()
        pos["status"] = "closed"
        self.capital += price * pos["quantity"] * 0.1 + pnl
        del self.positions[code]
    
    def update_positions(self, prices: Dict[str, float]):
        for code, pos in list(self.positions.items()):
            if code in prices:
                curr = prices[code]
                pnl = (curr - pos["entry"]) * pos["quantity"] * 0.5
                pos["pnl"] = round(pnl, 2)
                
                # Check stop loss / take profit
                if pos["action"].startswith("BUY CALL"):
                    if curr <= pos["stop"] or curr >= pos["target"]:
                        self.close_position(code, curr)
                elif pos["action"].startswith("BUY PUT"):
                    if curr >= pos["stop"] or curr <= pos["target"]:
                        self.close_position(code, curr)
    
    def get_state(self) -> dict:
        return {
            "auto_trade": self.auto_trade,
            "capital": round(self.capital, 2),
            "positions": list(self.positions.values()),
            "trades": self.trade_log[-20:] if self.trade_log else [],
            "trade_count": len(self.trade_log),
        }
