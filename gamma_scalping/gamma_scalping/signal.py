"""信号引擎"""

from __future__ import annotations

import datetime
import logging
from typing import Optional

from .config import Config
from .models import (
   GreeksSnapshot, PortfolioState,
   SignalType, Signal,
)

logger = logging.getLogger("GammaScalping.Signal")


class SignalEngine:
   """信号引擎
   
   监控组合 Delta，判断是否触发再平衡或止损信号。
   """
   
   def __init__(self, config: Config):
       self._cfg = config
       self._last_signal: Optional[Signal] = None
       self._signal_count: int = 0
   
   def evaluate(
       self,
       state: PortfolioState,
       atr_value: float = 0.0,
       day_change_pct: float = 0.0,
  ) -> Optional[Signal]:
       """评估当前状态，返回交易信号
       
       Args:
           state: 组合状态
           atr_value: 当前 ATR 值
           day_change_pct: 正股当日涨跌幅
       
       Returns:
           Signal 或 None（无操作）
       """
       now = datetime.datetime.now()
       
       # 1. 检查止损条件
       if self._check_stop_loss(day_change_pct, atr_value, state.underlying_price):
           signal = Signal(
               timestamp=now,
               signal_type=SignalType.STOP_LOSS,
               underlying_price=state.underlying_price,
               net_delta=state.net_delta,
               reason=f"止损触发: 当日涨跌幅={day_change_pct:.2%}, "
                      f"ATR={atr_value:.2f}, "
                      f"阈值={self._cfg.stop_loss_atr_multiple}*ATR"
           )
           self._last_signal = signal
           self._signal_count += 1
           logger.warning(signal.reason)
           return signal
       
       # 2. 检查再平衡条件
       if self._check_rebalance(state):
           rebalance_shares = self._calc_rebalance_shares(state)
           side = "买入" if rebalance_shares > 0 else "卖出"
           signal = Signal(
               timestamp=now,
               signal_type=(
                   SignalType.REBALANCE_BUY if rebalance_shares > 0
                   else SignalType.REBALANCE_SELL
               ),
               underlying_price=state.underlying_price,
               net_delta=state.net_delta,
               rebalance_shares=rebalance_shares,
               reason=f"Delta 再平衡: 净 Delta={state.net_delta:.4f}, "
                      f"需{side} {abs(rebalance_shares)}股"
           )
           self._last_signal = signal
           self._signal_count += 1
           logger.info(signal.reason)
           return signal
       
       return None
   
   def _check_stop_loss(self, day_change_pct: float, atr_value: float, price: float) -> bool:
       """检查止损条件"""
       if atr_value <= 0 or price <= 0:
           return False
       
       threshold = self._cfg.stop_loss_atr_multiple * atr_value / price
       return abs(day_change_pct) > threshold
   
   def _check_rebalance(self, state: PortfolioState) -> bool:
       """检查是否需要再平衡"""
       if not state.is_hedged:
           return False
       
       if not state.option_code:
           return False
       
       threshold = self._get_threshold()
       return abs(state.net_delta) > threshold
   
   def _calc_rebalance_shares(self, state: PortfolioState) -> int:
       """计算需要调整的正股数量
       
       返回正数表示买入，负数表示卖出。
       目标是使组合 Delta = 0。
       调整量是 100 的倍数。
       """
       lot = self._cfg.lot_size
       
       # 理想仓位 = -净 Delta（因为 Delta 偏正时需要卖出）
       target_shares = -round(state.net_delta)
       
       # 对齐到 100 股倍数
       target_shares = round(target_shares / lot) * lot
       
       # 实际需要调整的量
       delta = target_shares - state.stock_shares
       
       # 对齐到 100 股倍数
       delta = round(delta / lot) * lot
       
       return delta
   
   def _get_threshold(self) -> float:
       """获取当前再平衡阈值"""
       return self._cfg.rebalance_threshold
   
   def check_close_signal(self, minutes_to_close: int) -> bool:
       """检查是否接近收盘需要平仓"""
       return minutes_to_close <= self._cfg.close_before_end_min
   
   @property
   def last_signal(self) -> Optional[Signal]:
       return self._last_signal
   
   @property
   def signal_count(self) -> int:
       return self._signal_count
   
   def reset_count(self):
       self._signal_count = 0
