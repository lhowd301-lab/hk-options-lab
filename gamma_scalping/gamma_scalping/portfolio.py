"""组合状态管理"""

from __future__ import annotations

import datetime
import logging
from typing import Optional

from .config import Config
from .models import (
   GreeksSnapshot, PortfolioState, OptionSide, TradeRecord,
)

logger = logging.getLogger("GammaScalping.Portfolio")


class PortfolioManager:
   """组合管理器
   
   维护期权和正股持仓状态，计算组合 Delta/Gamma 等风险暴露。
   """
   
   def __init__(self, config: Config):
       self._cfg = config
       
       # 期权持仓
       self._option_code: Optional[str] = None
       self._option_contracts: int = 0
       self._option_cost: float = 0.0
       self._option_type: Optional[OptionSide] = None
       
       # 正股持仓
       self._stock_shares: int = 0   # 正数=多头，负数=空头
       self._stock_cost: float = 0.0
       
       # 盈亏
       self._realized_pnl: float = 0.0
       self._daily_pnl: float = 0.0
       self._trade_count: int = 0
       
       # 成交记录
       self._trades: list = []
   
   def open_option(self, option_code: str, contracts: int, price: float, opt_type: OptionSide) -> bool:
       """开仓期权"""
       if self._option_contracts > 0:
           logger.warning(f"已有期权持仓 {self._option_code}，无法重复开仓")
           return False
       
       self._option_code = option_code
       self._option_contracts = contracts
       self._option_cost = price
       self._option_type = opt_type
       
       logger.info(
           f"期权开仓: {option_code} x {contracts}张 "
           f"@ {price:.4f}, 类型={opt_type.value}"
       )
       return True
   
   def close_option(self, price: float) -> float:
       """平仓期权，返回盈亏"""
       if self._option_contracts == 0:
           return 0.0
       
       pnl = (price - self._option_cost) * self._option_contracts * self._cfg.option_multiplier
       self._realized_pnl += pnl
       self._daily_pnl += pnl
       
       logger.info(
           f"期权平仓: {self._option_code} x {self._option_contracts}张 "
           f"@ {price:.4f}, PnL={pnl:.2f}"
       )
       
       self._option_code = None
       self._option_contracts = 0
       self._option_cost = 0.0
       self._option_type = None
       return pnl
   
   def adjust_stock(self, delta_shares: int, price: float) -> Optional[TradeRecord]:
       """调整正股仓位
       
       Args:
           delta_shares: 需调整的股数（正数买入，负数卖出），必须是 100 的倍数
           price: 成交价格
       
       Returns:
           TradeRecord 或 None
       """
       if delta_shares == 0:
           return None
       
       # 确保是 100 的倍数
       if delta_shares % self._cfg.lot_size != 0:
           rounded = round(delta_shares / self._cfg.lot_size) * self._cfg.lot_size
           logger.debug(f"调整股数 {delta_shares} -> {rounded}（对齐到 100 股倍数）")
           delta_shares = rounded
       
       if delta_shares == 0:
           return None
       
       side = "BUY" if delta_shares > 0 else "SELL"
       abs_qty = abs(delta_shares)
       amount = abs_qty * price
       
       # 更新持仓
       if delta_shares > 0:
           # 买入：计算新的均价
           total_cost = self._stock_cost * abs(self._stock_shares) + amount
           self._stock_shares += delta_shares
           self._stock_cost = total_cost / abs(self._stock_shares) if self._stock_shares != 0 else price
       else:
           # 卖出：计算 scalp PnL
           sell_qty = min(abs_qty, abs(self._stock_shares))
           if self._stock_shares > 0:
               # 平多头
               scalp_pnl = (price - self._stock_cost) * sell_qty
               self._realized_pnl += scalp_pnl
               self._daily_pnl += scalp_pnl
           else:
               # 平空头
               scalp_pnl = (self._stock_cost - price) * sell_qty
               self._realized_pnl += scalp_pnl
               self._daily_pnl += scalp_pnl
           
           self._stock_shares += delta_shares  # delta_shares 为负数
           if self._stock_shares == 0:
               self._stock_cost = 0.0
       
       self._trade_count += 1
       
       record = TradeRecord(
           timestamp=datetime.datetime.now(),
           side=side,
           code=self._cfg.underlying_code,
           quantity=abs_qty,
           price=price,
           amount=amount,
           commission=self._calc_commission(amount),
           pnl=0 if delta_shares > 0 else (price - self._stock_cost) * abs_qty,
       )
       self._trades.append(record)
       
       logger.info(
           f"正股调整: {side} {abs_qty}股 @ {price:.2f}, "
           f"现持仓 {self._stock_shares}股, "
           f"累计 scalp PnL={self._realized_pnl:.2f}"
       )
       return record
   
   def close_all_stock(self, price: float) -> float:
       """平全部正股仓位，返回 PnL"""
       if self._stock_shares == 0:
           return 0.0
       
       qty = self._stock_shares
       side = "SELL" if qty > 0 else "BUY"
       amount = abs(qty) * price
       
       pnl = 0.0
       if qty > 0:
           pnl = (price - self._stock_cost) * qty
       else:
           pnl = (self._stock_cost - price) * abs(qty)
       
       self._realized_pnl += pnl
       self._daily_pnl += pnl
       self._stock_shares = 0
       self._stock_cost = 0.0
       
       logger.info(f"平正股仓位: {side} {abs(qty)}股 @ {price:.2f}, PnL={pnl:.2f}")
       return pnl
   
   def get_state(self, greeks: Optional[GreeksSnapshot] = None) -> PortfolioState:
       """获取当前组合状态"""
       now = datetime.datetime.now()
       
       state = PortfolioState(
           timestamp=now,
           underlying_price=greeks.underlying_price if greeks else 0.0,
           option_code=self._option_code,
           option_contracts=self._option_contracts,
           option_delta=greeks.delta if greeks else 0.0,
           option_gamma=greeks.gamma if greeks else 0.0,
           option_theta=greeks.theta if greeks else 0.0,
           option_cost=self._option_cost,
           stock_shares=self._stock_shares,
           stock_cost=self._stock_cost,
           realized_pnl=self._realized_pnl,
       )
       
       # 计算组合净 Delta
       if greeks and self._option_contracts > 0:
           opt_delta_total = greeks.delta * self._option_contracts * self._cfg.option_multiplier
           stock_delta = self._stock_shares
           state.net_delta = opt_delta_total + stock_delta
           state.net_gamma = greeks.gamma * self._option_contracts * self._cfg.option_multiplier
           state.theta_decay = greeks.theta * self._option_contracts * self._cfg.option_multiplier
           
           # 未实现盈亏
           opt_pnl = (greeks.option_price - self._option_cost) * self._option_contracts * self._cfg.option_multiplier
           stock_pnl = 0.0
           if self._stock_shares > 0:
               stock_pnl = (greeks.underlying_price - self._stock_cost) * self._stock_shares
           elif self._stock_shares < 0:
               stock_pnl = (self._stock_cost - greeks.underlying_price) * abs(self._stock_shares)
           state.unrealized_pnl = opt_pnl + stock_pnl
       
       return state
   
   def _calc_commission(self, amount: float) -> float:
       """计算交易成本"""
       commission = max(amount * self._cfg.commission_rate, self._cfg.min_commission)
       stamp = max(amount * self._cfg.stamp_duty_rate, 1.0)
       platform = self._cfg._get("trading_costs", "platform_fee", default=15.0)
       settlement = amount * self._cfg._get("trading_costs", "settlement_fee_rate", default=0.000027)
       return commission + stamp + platform + settlement
   
   def estimate_trade_cost(self, amount: float) -> float:
       """估算交易成本"""
       return self._calc_commission(amount)
   
   @property
   def option_code(self) -> Optional[str]:
       return self._option_code
   
   @property
   def option_contracts(self) -> int:
       return self._option_contracts
   
   @property
   def stock_shares(self) -> int:
       return self._stock_shares
   
   @property
   def realized_pnl(self) -> float:
       return self._realized_pnl
   
   @property
   def daily_pnl(self) -> float:
       return self._daily_pnl
   
   @property
   def trade_count(self) -> int:
       return self._trade_count
   
   def reset_daily(self):
       """重置日统计"""
       self._daily_pnl = 0.0
       self._trade_count = 0
       self._trades.clear()
   
   @property
   def is_option_open(self) -> bool:
       return self._option_contracts > 0
   
   @property
   def is_stock_open(self) -> bool:
       return self._stock_shares != 0
   
   @property
   def is_open(self) -> bool:
       return self.is_option_open or self.is_stock_open
   
   @property
   def trades(self) -> list:
       return list(self._trades)
