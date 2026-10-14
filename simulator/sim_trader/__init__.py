"""
智能模拟交易系统

基于富途API的模拟交易系统, 用于中芯国际(00981.HK)的策略回测与实时盯盘
"""
__version__ = "1.0.0"
from .config import CONFIG, TradingConfig
from .simulation_account import SimulationAccount, TradeRecord
from .strategy import TradingStrategy
from .connector import FutuConnector
from .dashboard import Dashboard
