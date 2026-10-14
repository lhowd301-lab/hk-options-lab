"""风控模块"""

from __future__ import annotations

import datetime
import logging
from typing import Optional

from .config import Config
from .models import SignalType, Signal
from .portfolio import PortfolioManager

logger = logging.getLogger("GammaScalping.Risk")


class RiskManager:
   """风险管理器
   
   监控止损条件、日亏损上限、收盘强制平仓。
   """
   
   def __init__(self, config: Config, portfolio: PortfolioManager):
       self._cfg = config
       self._portfolio = portfolio
       self._stop_loss_triggered: bool = False
       self._close_executed: bool = False
       self._day_start_pnl: float = 0.0
   
   def check_stop_loss(self, day_change_pct: float, atr_value: float, price: float) -> bool:
       """检查是否触发止损
       
       条件：正股当日涨跌幅超过 3 倍 ATR(14)
       """
       if self._stop_loss_triggered:
           return True
       
       if atr_value <= 0 or price <= 0:
           return False
       
       atr_pct = atr_value / price
       threshold = self._cfg.stop_loss_atr_multiple * atr_pct
       
       if abs(day_change_pct) > threshold:
           logger.warning(
               f"止损触发! 涨跌幅={day_change_pct:.2%}, "
               f"ATR%={atr_pct:.2%}, "
               f"阈值={threshold:.2%}"
           )
           self._stop_loss_triggered = True
           return True
       
       return False
   
   def check_daily_loss(self) -> bool:
       """检查单日亏损上限"""
       if self._cfg.max_daily_loss <= 0:
           return False
       
       daily_loss = self._portfolio.daily_pnl
       if daily_loss < -self._cfg.max_daily_loss:
           logger.warning(
               f"单日亏损上限触发: 当前亏损 {-daily_loss:.2f}, "
               f"上限 {self._cfg.max_daily_loss:.2f}"
           )
           return True
       
       return False
   
   def check_close_time(self, now: Optional[datetime.datetime] = None) -> bool:
       """检查是否到达收盘平仓时间
       
       收盘前 N 分钟，必须平掉所有头寸。
       """
       if now is None:
           now = datetime.datetime.now()
       
       hk_now = self._to_hk_time(now)
       close_time = self._parse_time(self._cfg.market_close)
       close_min = close_time.hour * 60 + close_time.minute
       now_min = hk_now.hour * 60 + hk_now.minute
       
       minutes_to_close = close_min - now_min
       
       if minutes_to_close <= self._cfg.close_before_end_min:
           logger.info(
               f"距离收盘 {minutes_to_close} 分钟，准备平仓"
           )
           return True
       
       return False
   
   def check_market_hours(self, now: Optional[datetime.datetime] = None) -> bool:
       """检查是否在交易时间内"""
       if now is None:
           now = datetime.datetime.now()
       
       hk_now = self._to_hk_time(now)
       now_min = hk_now.hour * 60 + hk_now.minute
       
       open_time = self._parse_time(self._cfg.market_open)
       lunch_start = self._parse_time("12:00")
       lunch_end = self._parse_time("13:00")
       close_time = self._parse_time(self._cfg.market_close)
       
       open_min = open_time.hour * 60 + open_time.minute
       lunch_start_min = lunch_start.hour * 60 + lunch_start.minute
       lunch_end_min = lunch_end.hour * 60 + lunch_end.minute
       close_min = close_time.hour * 60 + close_time.minute
       
       morning = open_min <= now_min < lunch_start_min
       afternoon = lunch_end_min <= now_min < close_min
       
       return morning or afternoon
   
   def check_trade_limit(self) -> bool:
       """检查每日交易次数限制"""
       return self._portfolio.trade_count < self._cfg.max_daily_trades
   
   def _to_hk_time(self, dt: datetime.datetime) -> datetime.datetime:
       """转换为香港时间"""
       from zoneinfo import ZoneInfo
       try:
           hk_tz = ZoneInfo("Asia/Hong_Kong")
           if dt.tzinfo is None:
               local_tz = ZoneInfo("Asia/Shanghai")  # 假设本地为北京时间
               dt = dt.replace(tzinfo=local_tz)
           return dt.astimezone(hk_tz)
       except Exception:
           return dt
   
   def _parse_time(self, time_str: str) -> datetime.time:
       parts = time_str.split(":")
       return datetime.time(int(parts[0]), int(parts[1]))
   
   def reset(self):
       """重置风控状态（新交易日）"""
       self._stop_loss_triggered = False
       self._close_executed = False
       self._portfolio.reset_daily()
       logger.info("风控状态已重置")
   
   @property
   def is_stopped(self) -> bool:
       return self._stop_loss_triggered
   
   @property
   def close_executed(self) -> bool:
       return self._close_executed
   
   def mark_close_executed(self):
       self._close_executed = True
