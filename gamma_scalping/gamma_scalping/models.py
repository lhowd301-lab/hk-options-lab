"""数据模型定义"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


class OptionSide(Enum):
   CALL = "CALL"
   PUT = "PUT"


class SignalType(Enum):
   NONE = auto()           # 无需操作
   REBALANCE_BUY = auto()  # 买入正股（Delta 偏负）
   REBALANCE_SELL = auto() # 卖出正股（Delta 偏正）
   STOP_LOSS = auto()      # 止损离场
   CLOSE_ALL = auto()      # 强制平仓（收盘）


@dataclass
class GreeksSnapshot:
   """期权希腊值快照"""
   timestamp: datetime.datetime
   option_code: str
   underlying_price: float
   option_price: float
   delta: float
   gamma: float
   theta: float
   vega: float
   rho: float
   implied_volatility: float
   strike_price: float
   days_to_expiry: int
   option_type: OptionSide


@dataclass
class PortfolioState:
   """组合状态"""
   timestamp: datetime.datetime
   underlying_price: float
   
   # 期权持仓
   option_code: Optional[str] = None
   option_contracts: int = 0        # 张数
   option_delta: float = 0.0       # 单张 Delta
   option_gamma: float = 0.0       # 单张 Gamma
   option_theta: float = 0.0       # 单张 Theta
   option_cost: float = 0.0        # 开仓成本价
   
   # 正股持仓
   stock_shares: int = 0            # 股数（正数为多，负数为空）
   stock_cost: float = 0.0          # 持仓均价
   
   # 计算结果
   net_delta: float = 0.0           # 组合净 Delta
   net_gamma: float = 0.0           # 组合净 Gamma
   theta_decay: float = 0.0         # 当日 Theta 损耗
   unrealized_pnl: float = 0.0      # 未实现盈亏
   realized_pnl: float = 0.0        # 已实现盈亏（scalp 累计）
   
   @property
   def is_hedged(self) -> bool:
       return abs(self.net_delta) < 0.5
   
   @property
   def delta_exposure_shares(self) -> int:
       """期权 Delta 对应的正股股数暴露"""
       return round(self.option_delta * self.option_contracts * 100)


@dataclass
class Signal:
   """交易信号"""
   timestamp: datetime.datetime
   signal_type: SignalType
   underlying_price: float
   net_delta: float
   rebalance_shares: int = 0        # 需调整的正股数量
   reason: str = ""


@dataclass
class OptionContract:
   """期权合约信息"""
   code: str
   name: str
   option_type: OptionSide
   strike_price: float
   expiry_date: datetime.date
   days_to_expiry: int
   delta: float
   gamma: float
   theta: float
   vega: float
   implied_volatility: float
   last_price: float
   bid_price: float
   ask_price: float


@dataclass
class TradeRecord:
   """成交记录"""
   timestamp: datetime.datetime
   side: str                       # BUY / SELL
   code: str                       # 证券代码
   quantity: int                   # 数量
   price: float                    # 成交价
   amount: float                   # 成交额
   commission: float = 0.0         # 佣金
   pnl: float = 0.0               # 本次盈亏（scalp）
   order_id: int = 0


@dataclass
class GreeksRecord:
   """希腊值日志记录"""
   timestamp: datetime.datetime
   underlying_price: float
   option_code: str
   option_price: float
   delta: float
   gamma: float
   theta: float
   vega: float
   iv: float
   net_delta: float
   stock_shares: int
   source: str = "api"  # api 或 bs_model
