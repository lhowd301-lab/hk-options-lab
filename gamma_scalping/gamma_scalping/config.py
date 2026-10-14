"""配置加载器"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import yaml


class Config:
   """全局配置"""
   
   _instance: "Config" = None
   
   def __init__(self, path: str = "config.yaml"):
       self.path = path
       self._data: Dict[str, Any] = {}
       self.reload()
   
   @classmethod
   def load(cls, path: str = "config.yaml") -> "Config":
       if cls._instance is None:
           cls._instance = cls(path)
       return cls._instance
   
   def reload(self) -> None:
       config_path = Path(self.path)
       if not config_path.exists():
           raise FileNotFoundError(f"Config file not found: {self.path}")
       with open(config_path, "r", encoding="utf-8") as f:
           self._data = yaml.safe_load(f)
   
   def _get(self, *keys: str, default: Any = None) -> Any:
       d = self._data
       for k in keys:
           if isinstance(d, dict):
               d = d.get(k)
               if d is None:
                   return default
           else:
               return default
       return d if d is not None else default
   
   # === 标的 ===
   @property
   def underlying_code(self) -> str:
       return self._get("underlying", "code", default="HK.00700")
   
   @property
   def lot_size(self) -> int:
       return self._get("underlying", "lot_size", default=100)
   
   @property
   def option_multiplier(self) -> int:
       return self._get("underlying", "option_multiplier", default=100)
   
   # === 期权选择 ===
   @property
   def expiry_min_days(self) -> int:
       return self._get("option_selection", "expiry_min_days", default=5)
   
   @property
   def expiry_max_days(self) -> int:
       return self._get("option_selection", "expiry_max_days", default=20)
   
   @property
   def delta_min(self) -> float:
       return self._get("option_selection", "delta_min", default=0.35)
   
   @property
   def delta_max(self) -> float:
       return self._get("option_selection", "delta_max", default=0.65)
   
   @property
   def option_type(self) -> str:
       return self._get("option_selection", "option_type", default="CALL")
   
   # === 策略 ===
   @property
   def rebalance_threshold(self) -> float:
       return self._get("strategy", "rebalance_threshold", default=0.1)
   
   @property
   def atr_period(self) -> int:
       return self._get("strategy", "atr_period", default=14)
   
   @property
   def stop_loss_atr_multiple(self) -> float:
       return self._get("strategy", "stop_loss_atr_multiple", default=3.0)
   
   @property
   def close_before_end_min(self) -> int:
       return self._get("strategy", "close_before_market_end_min", default=5)
   
   @property
   def max_daily_loss(self) -> float:
       return self._get("strategy", "max_daily_loss", default=0.0)
   
   # === 交易成本 ===
   @property
   def commission_rate(self) -> float:
       return self._get("trading_costs", "commission_rate", default=0.0025)
   
   @property
   def min_commission(self) -> float:
       return self._get("trading_costs", "min_commission", default=5.0)
   
   @property
   def stamp_duty_rate(self) -> float:
       return self._get("trading_costs", "stamp_duty_rate", default=0.0013)
   
   @property
   def min_scalp_profit(self) -> float:
       return self._get("trading_costs", "min_scalp_profit", default=50.0)
   
   # === FutuOpenD ===
   @property
   def futu_host(self) -> str:
       return self._get("futu", "host", default="127.0.0.1")
   
   @property
   def futu_quote_port(self) -> int:
       return self._get("futu", "quote_port", default=11111)
   
   @property
   def futu_trade_port(self) -> int:
       return self._get("futu", "trade_port", default=11111)
   
   @property
   def futu_trade_env(self) -> str:
       return self._get("futu", "trade_env", default="SIMULATE")
   
   @property
   def futu_trd_market(self) -> str:
       return self._get("futu", "trd_market", default="HK")
   
   @property
   def futu_password(self) -> str:
       return self._get("futu", "password", default="")
   
   # === BS 模型 ===
   @property
   def risk_free_rate(self) -> float:
       return self._get("bs_model", "risk_free_rate", default=0.035)
   
   @property
   def dividend_yield(self) -> float:
       return self._get("bs_model", "dividend_yield", default=0.008)
   
   @property
   def default_iv(self) -> float:
       return self._get("bs_model", "default_iv", default=0.30)
   
   # === 风控 ===
   @property
   def max_option_contracts(self) -> int:
       return self._get("risk", "max_option_contracts", default=2)
   
   @property
   def max_daily_trades(self) -> int:
       return self._get("risk", "max_daily_trades", default=50)
   
   # === 市场时间 ===
   @property
   def market_open(self) -> str:
       return self._get("market_hours", "open", default="09:30")
   
   @property
   def market_close(self) -> str:
       return self._get("market_hours", "close", default="16:00")
   
   @property
   def market_timezone(self) -> str:
       return self._get("market_hours", "timezone", default="Asia/Hong_Kong")
   
   # === 日志 ===
   @property
   def log_level(self) -> str:
       return self._get("logging", "level", default="INFO")
   
   @property
   def log_file(self) -> str:
       return self._get("logging", "file", default="logs/gamma_scalping.log")
   
   @property
   def log_max_bytes(self) -> int:
       return self._get("logging", "max_bytes", default=52428800)
   
   @property
   def log_backup_count(self) -> int:
       return self._get("logging", "backup_count", default=7)
