"""
智能模拟交易系统 - 配置管理
"""
from dataclasses import dataclass, field
from typing import Optional
from datetime import time


@dataclass
class TradingConfig:
    """交易系统配置"""

    # === 标的 ===
    stock_code: str = "HK.00981"           # 中芯国际 (港股)
    stock_name: str = "中芯国际"

    # === Futu API 连接 ===
    futu_host: str = "127.0.0.1"
    futu_quote_port: int = 11111
    futu_trd_port: int = 11112
    futu_pwd: Optional[str] = None
    unlock_pwd: Optional[str] = None

    # === 模拟账户初始资金 ===
    initial_cash: float = 500_000.0       # 初始现金 (HKD)

    # === 策略参数 ===
    avg_minutes: int = 30                 # 前 N 分钟作为基准时段
    buy_ratio: float = 1.0 / 10.0         # 买入 = 持仓市值的 1/10
    stop_loss_ratio: float = -0.5 / 100.0  # 低于均价的 1/10 时清仓

    # === 基准时段 (港股 09:30-16:00) ===
    market_open: time = field(default_factory=lambda: time(9, 30))

    # === 显示 ===
    refresh_interval: float = 1.0
    trade_log_max: int = 20

    @property
    def avg_end_time(self) -> time:
        """基准时段结束时间"""
        from datetime import timedelta, datetime, date
        dt = datetime.combine(date.today(), self.market_open) + timedelta(minutes=self.avg_minutes)
        return dt.time()

    @property
    def stop_loss_price_ratio(self) -> float:
        """清仓阈值比例"""
        return 1.0 + self.stop_loss_ratio


# 全局单例
CONFIG = TradingConfig()
