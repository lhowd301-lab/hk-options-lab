"""
智能模拟交易系统 - 模拟账户
"""
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime
from .config import CONFIG


@dataclass
class TradeRecord:
    """交易记录"""
    time: str           # HH:MM:SS
    action: str         # 买入 / 卖出
    price: float        # 成交价
    shares: int         # 成交股数
    amount: float       # 成交金额
    cash_after: float   # 操作后现金
    pos_after: int      # 操作后持仓


@dataclass
class SimulationAccount:
    """模拟账户"""
    initial_cash: float = CONFIG.initial_cash
    cash: float = CONFIG.initial_cash
    position: int = 0           # 持仓股数
    avg_cost: float = 0.0       # 持仓成本均价
    trade_log: List[TradeRecord] = field(default_factory=list)

    # 日内策略状态
    avg_price_30min: Optional[float] = None   # 前30分钟均价
    avg_set_time: Optional[str] = None         # 均价设定时间
    is_avg_period: bool = True                 # 是否还在基准统计时段

    @property
    def position_value(self) -> float:
        """持仓市值 (依赖外部传入当前价)"""
        return 0.0

    def market_value(self, current_price: float) -> float:
        """当前持仓市值"""
        return self.position * current_price

    def total_assets(self, current_price: float) -> float:
        """总资产 = 现金 + 持仓市值"""
        return self.cash + self.market_value(current_price)

    def pnl(self, current_price: float) -> float:
        """盈亏 = 总资产 - 初始现金"""
        return self.total_assets(current_price) - self.initial_cash

    def pnl_pct(self, current_price: float) -> float:
        """收益率"""
        if self.initial_cash <= 0:
            return 0.0
        return (self.total_assets(current_price) - self.initial_cash) / self.initial_cash * 100

    def buy(self, price: float, shares: int):
        """模拟买入"""
        cost = round(shares * price, 3)
        if cost > self.cash:
            # 不够钱就全买
            shares = int(self.cash / price)
            if shares <= 0:
                return False
            cost = round(shares * price, 3)

        # 更新持仓成本
        total_cost = self.avg_cost * self.position + cost
        self.position += shares
        self.cash -= cost
        self.avg_cost = total_cost / self.position if self.position > 0 else 0.0

        now = datetime.now().strftime("%H:%M:%S")
        record = TradeRecord(
            time=now, action="买入", price=price,
            shares=shares, amount=cost,
            cash_after=self.cash, pos_after=self.position,
        )
        self.trade_log.append(record)
        return True

    def sell_all(self, price: float) -> bool:
        """模拟全部清仓"""
        if self.position <= 0:
            return False

        amount = round(self.position * price, 3)
        self.cash += amount
        sold_shares = self.position
        self.position = 0
        self.avg_cost = 0.0

        now = datetime.now().strftime("%H:%M:%S")
        record = TradeRecord(
            time=now, action="卖出", price=price,
            shares=sold_shares, amount=amount,
            cash_after=self.cash, pos_after=self.position,
        )
        self.trade_log.append(record)
        return True

    def recent_trades(self, n: int = 5) -> List[TradeRecord]:
        """最近 N 条交易"""
        return self.trade_log[-n:] if self.trade_log else []

    def __str__(self, current_price: float) -> str:
        mkt_val = self.market_value(current_price)
        total = self.total_assets(current_price)
        pnl_val = self.pnl(current_price)
        pnl_pct = self.pnl_pct(current_price)

        lines = [
            f"现金: {self.cash:>12,.2f}",
            f"持仓: {self.position:>10} 股",
            f"市值: {mkt_val:>12,.2f}",
            f"总资产: {total:>12,.2f}",
            f"盈亏: {pnl_val:>+10,.2f} ({pnl_pct:>+.2f}%)",
        ]
        return "\n".join(lines)
    def sell_all(self, price: float) -> bool:
        """模拟全部清仓"""
    def sell(self, price: float, shares: int) -> bool:
        """模拟卖出指定股数"""
        if shares <= 0 or shares > self.position:
            return False
        amount = round(shares * price, 3)
        self.cash += amount
        self.position -= shares
        if self.position == 0:
            self.avg_cost = 0.0
        now = datetime.now().strftime("%H:%M:%S")
        record = TradeRecord(
            time=now, action="卖出", price=price,
            shares=shares, amount=amount,
            cash_after=self.cash, pos_after=self.position,
        )
        self.trade_log.append(record)
        return True

    def sell_all(self, price: float) -> bool:
        """模拟全部清仓"""
