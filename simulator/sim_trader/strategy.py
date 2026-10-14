"""
智能模拟交易系统 - 交易策略引擎

策略:
  1. 滚动窗口取最近30个价格的均值
  2. 当前价 > 均价 -> 买入持仓市值的 1/10 (高频)
  3. 当前价 < 均价 x 0.995 -> 全部清仓
"""
import logging
from typing import Optional
from collections import deque
from datetime import datetime
from .config import CONFIG
from .simulation_account import SimulationAccount

logger = logging.getLogger("strategy")


class TradingStrategy:

    def __init__(self, account: SimulationAccount):
        self.account = account
        self.prices_window = deque(maxlen=CONFIG.avg_minutes)
        self._ready = False
        self._last_signal = "等待基准数据..."

    @property
    def avg_price(self) -> Optional[float]:
        return self.account.avg_price_30min

    @property
    def stop_loss_price(self) -> Optional[float]:
        if self.avg_price is None:
            return None
        return self.avg_price * CONFIG.stop_loss_price_ratio

    def feed_price(self, price: float, timestamp: Optional[str] = None) -> Optional[str]:
        if price <= 0:
            return None
        self.prices_window.append(price)
        self._update_avg()
        if not self._ready:
            return None
        return self._evaluate_trade(price)

    def _update_avg(self):
        if len(self.prices_window) < CONFIG.avg_minutes:
            self._last_signal = f"收集中 {len(self.prices_window)}/{CONFIG.avg_minutes}"
            return
        avg = sum(self.prices_window) / len(self.prices_window)
        self.account.avg_price_30min = round(avg, 4)
        if not self._ready:
            self._ready = True
            logger.info("滚动均价就绪 = %.4f (窗口 %d个价格点)", avg, len(self.prices_window))
        self._last_signal = f"滚动均 {avg:.4f} | 买入 > {avg:.4f} | 止损 < {self.stop_loss_price:.4f}"

    def _evaluate_trade(self, price: float) -> Optional[str]:
        if self.avg_price is None:
            return None
        acct = self.account
        sl = self.stop_loss_price
        if sl is not None and price < sl and acct.position > 0:
            acct.sell_all(price)
            msg = f"止损清仓! {price:.4f} < {sl:.4f}"
            logger.warning(msg)
            self._last_signal = msg
            return msg
        if price > self.avg_price:
            self._execute_buy(price)
            return self._last_signal
        diff = price - self.avg_price
        self._last_signal = f"现价 {price:.4f} | 均 {self.avg_price:.4f} | 差 {diff:+.4f}"
        return None

    def _execute_buy(self, price: float):
        acct = self.account
        if acct.position == 0:
            amt = acct.cash * CONFIG.buy_ratio
        else:
            amt = acct.market_value(price) * CONFIG.buy_ratio
        shares = int(amt / price)
        if shares <= 0:
            return
        acct.buy(price, shares)
        self._last_signal = f"买入 {shares} 股 @ {price:.4f} | 持仓 {acct.position}"

    def get_signal_text(self) -> str:
        return self._last_signal or "等待..."
