"""执行引擎"""

from __future__ import annotations

import datetime
import logging
from typing import Optional, Tuple

from futu import (
   OpenSecTradeContext, TrdEnv, TrdSide, OrderType,
   TrdMarket, RET_OK,
)

from .config import Config
from .models import (
   PortfolioState, Signal, SignalType,
   TradeRecord,
)
from .portfolio import PortfolioManager

logger = logging.getLogger("GammaScalping.Execution")


class ExecutionEngine:
   """执行引擎
   
   接收信号，通过富途 API 执行下单操作。
   强制使用 TrdEnv.SIMULATE 模拟环境。
   """
   
   def __init__(self, trade_ctx: OpenSecTradeContext, portfolio: PortfolioManager, config: Config):
       self._ctx = trade_ctx
       self._portfolio = portfolio
       self._cfg = config
       self._acc_id: Optional[int] = None
       self._order_history: list = []
   
   def set_account(self, acc_id: int):
       """设置交易账户 ID"""
       self._acc_id = acc_id
   
   def execute_signal(self, signal: Signal, state: PortfolioState) -> Optional[TradeRecord]:
       """执行交易信号
       
       Args:
           signal: 交易信号
           state: 当前组合状态
       
       Returns:
           TradeRecord 或 None
       """
       if signal.signal_type == SignalType.NONE:
           return None
       
       if signal.signal_type == SignalType.REBALANCE_BUY:
           return self._buy_stock(signal.rebalance_shares, signal.underlying_price)
       
       if signal.signal_type == SignalType.REBALANCE_SELL:
           return self._sell_stock(abs(signal.rebalance_shares), signal.underlying_price)
       
       if signal.signal_type == SignalType.STOP_LOSS:
           return self._close_all(signal.underlying_price)
       
       if signal.signal_type == SignalType.CLOSE_ALL:
           return self._close_all(signal.underlying_price)
       
       return None
   
   def open_initial_position(
       self,
       option_code: str,
       option_price: float,
       option_delta: float,
       contracts: int = 1,
   ) -> bool:
       """开仓初始头寸
       
       买入 1 张期权 + 卖出 Delta 份正股对冲。
       """
       # 1. 买入期权
       if not self._place_option_order(option_code, TrdSide.BUY, contracts, option_price):
           logger.error("期权开仓失败")
           return False
       
       logger.info(f"期权开仓成功: {option_code} x {contracts} @ {option_price:.4f}")
       
       # 2. 计算对冲所需正股数量
       hedge_shares = round(option_delta * contracts * self._cfg.option_multiplier)
       
       if hedge_shares > 0:
           # Delta 为正，需要卖出正股
           if not self._place_stock_order(TrdSide.SELL, hedge_shares, option_price):
               logger.error("对冲正股卖出失败")
               return False
           logger.info(f"对冲卖出: {hedge_shares}股 @ {option_price:.2f}")
       
       # 3. 更新组合状态
       from .models import OptionSide
       opt_type = OptionSide.CALL  # 默认为 CALL
       self._portfolio.open_option(option_code, contracts, option_price, opt_type)
       if hedge_shares > 0:
           self._portfolio.adjust_stock(-hedge_shares, option_price)
       
       logger.info(
           f"初始仓位建立完成: 期权 {contracts}张 + 正股 {-hedge_shares if hedge_shares > 0 else 0}股"
       )
       return True
   
   def _buy_stock(self, shares: int, price: float) -> Optional[TradeRecord]:
       """买入正股"""
       if shares <= 0:
           return None
       
       if not self._place_stock_order(TrdSide.BUY, shares, price):
           logger.error(f"买入正股失败: {shares}股 @ {price:.2f}")
           return None
       
       return self._portfolio.adjust_stock(shares, price)
   
   def _sell_stock(self, shares: int, price: float) -> Optional[TradeRecord]:
       """卖出正股"""
       if shares <= 0:
           return None
       
       if not self._place_stock_order(TrdSide.SELL, shares, price):
           logger.error(f"卖出正股失败: {shares}股 @ {price:.2f}")
           return None
       
       return self._portfolio.adjust_stock(-shares, price)
   
   def _close_all(self, price: float) -> Optional[TradeRecord]:
       """平掉所有头寸"""
       logger.warning("开始平掉全部头寸...")
       
       # 平正股
       if self._portfolio.stock_shares != 0:
           side = TrdSide.SELL if self._portfolio.stock_shares > 0 else TrdSide.BUY
           qty = abs(self._portfolio.stock_shares)
           if self._place_stock_order(side, qty, price):
               self._portfolio.close_all_stock(price)
       
       # 平期权
       if self._portfolio.option_contracts > 0:
           if self._place_option_order(
               self._portfolio.option_code,
               TrdSide.SELL,
               self._portfolio.option_contracts,
               price,
           ):
               self._portfolio.close_option(price)
       
       logger.warning("全部头寸已平仓")
       return None
   
   def _place_stock_order(self, side: TrdSide, qty: int, price: float) -> bool:
       """下正股订单"""
       if self._acc_id is None:
           logger.error("未设置交易账户")
           return False
       
       try:
           from futu import PlaceOrder, TrdEnv
           
           order = PlaceOrder.pack_req(
               trd_side=side,
               order_type=OrderType.NORMAL,
               price=price,
               qty=qty,
               code=self._cfg.underlying_code,
               adjust_limit=0,
               trd_env=TrdEnv.SIMULATE,
               sec_mkt_str=self._cfg.futu_trd_market,
               acc_id=self._acc_id,
               trd_mkt=TrdMarket.HK,
               conn_id=0,
               remark="gamma_scalp",
               time_in_force=0,
               fill_outside_rth=False,
               session=0,
               aux_price=0.0,
               trail_type=0,
               trail_value=0.0,
               trail_spread=0.0,
               jp_acc_type=0,
               position_id=0,
               expire_time="",
               amount=0.0,
               pred_side=0,
           )
           
           ret, data = self._ctx.place_order(order)
           if ret != RET_OK:
               logger.error(f"下单失败: {data}")
               return False
           
           order_id = data.get("order_id", 0) if isinstance(data, dict) else 0
           logger.info(
               f"订单已提交: {'BUY' if side == TrdSide.BUY else 'SELL'} "
               f"{qty}股 {self._cfg.underlying_code} "
               f"@ {price:.2f}, 订单ID={order_id}"
           )
           return True
           
       except Exception as e:
           logger.error(f"下单异常: {e}")
           return False
   
   def _place_option_order(self, code: str, side: TrdSide, qty: int, price: float) -> bool:
       """下期权订单"""
       if self._acc_id is None:
           logger.error("未设置交易账户")
           return False
       
       try:
           from futu import PlaceOrder, TrdEnv
           
           order = PlaceOrder.pack_req(
               trd_side=side,
               order_type=OrderType.NORMAL,
               price=price,
               qty=qty,
               code=code,
               adjust_limit=0,
               trd_env=TrdEnv.SIMULATE,
               sec_mkt_str=self._cfg.futu_trd_market,
               acc_id=self._acc_id,
               trd_mkt=TrdMarket.HK,
               conn_id=0,
               remark="gamma_scalp_opt",
               time_in_force=0,
               fill_outside_rth=False,
               session=0,
               aux_price=0.0,
               trail_type=0,
               trail_value=0.0,
               trail_spread=0.0,
               jp_acc_type=0,
               position_id=0,
               expire_time="",
               amount=0.0,
               pred_side=0,
           )
           
           ret, data = self._ctx.place_order(order)
           if ret != RET_OK:
               logger.error(f"期权下单失败: {data}")
               return False
           
           order_id = data.get("order_id", 0) if isinstance(data, dict) else 0
           logger.info(
               f"期权订单已提交: {'BUY' if side == TrdSide.BUY else 'SELL'} "
               f"{qty}张 {code} @ {price:.4f}, 订单ID={order_id}"
           )
           return True
           
       except Exception as e:
           logger.error(f"期权下单异常: {e}")
           return False
   
   @property
   def order_history(self) -> list:
       return list(self._order_history)
