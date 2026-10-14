"""希腊值引擎"""

from __future__ import annotations

import datetime
import logging
from typing import Optional

from futu import (
   OpenQuoteContext, OptionStrategyLeg, StrategyLegAction,
   RET_OK, RET_ERROR,
)

from .config import Config
from .models import GreeksSnapshot, OptionSide
from .bs_model import compute_greeks_from_bs, calculate_iv

logger = logging.getLogger("GammaScalping.Greeks")


class GreeksEngine:
   """实时希腊值引擎
   
   优先从富途 API 获取希腊值，API 不可用时以 BS 模型后备计算。
   """
   
   def __init__(self, quote_ctx: OpenQuoteContext, config: Config):
       self._ctx = quote_ctx
       self._cfg = config
       self._last_greeks: Optional[GreeksSnapshot] = None
       self._underlying_price: float = 0.0
       self._last_greeks_source: str = "none"
   
   def update_underlying_price(self, price: float):
       """更新正股价格"""
       self._underlying_price = price
   
   def fetch_greeks(self, option_code: str, underlying_price: Optional[float] = None) -> Optional[GreeksSnapshot]:
       """获取期权希腊值
       
       Args:
           option_code: 期权合约代码
           underlying_price: 当前正股价格（可选，默认使用缓存值）
       
       Returns:
           GreeksSnapshot 或 None
       """
       price = underlying_price or self._underlying_price
       if price <= 0:
           logger.warning("正股价格无效，无法获取希腊值")
           return None
       
       # 优先从 API 获取
       snapshot = self._fetch_from_api(option_code, price)
       if snapshot:
           self._last_greeks = snapshot
           self._last_greeks_source = "api"
           return snapshot
       
       # API 不可用时用 BS 模型后备
       snapshot = self._compute_bs_fallback(option_code, price)
       if snapshot:
           self._last_greeks = snapshot
           self._last_greeks_source = "bs_model"
           logger.info(f"使用 BS 后备计算希腊值: {option_code}")
           return snapshot
       
       logger.error(f"无法获取希腊值: {option_code}")
       return None
   
   def _fetch_from_api(self, option_code: str, underlying_price: float) -> Optional[GreeksSnapshot]:
       """从富途 API 获取希腊值"""
       try:
           leg = OptionStrategyLeg()
           leg.code = option_code
           leg.quantity = 1
           leg.action = StrategyLegAction.UNKNOWN

           ret, data = self._ctx.get_option_quote([leg])
           if ret != RET_OK or data is None or len(data) == 0:
               return None
           
           row = data.iloc[0]
           
           # 检查 Delta 是否有效
           delta = float(row.get("delta", 0) or 0)
           if abs(delta) < 0.001:
               # Delta 为 0 可能表示 API 未返回有效希腊值
               logger.debug("API 返回的 Delta 为 0，尝试 BS 后备")
               return None
           
           opt_type_str = str(row.get("option_type", ""))
           opt_side = OptionSide.CALL if "CALL" in opt_type_str.upper() else OptionSide.PUT
           
           now = datetime.datetime.now()
           expire_str = str(row.get("expire_time", ""))
           
           snapshot = GreeksSnapshot(
               timestamp=now,
               option_code=option_code,
               underlying_price=underlying_price,
               option_price=float(row.get("price", 0) or 0),
               delta=delta,
               gamma=float(row.get("gamma", 0) or 0),
               theta=float(row.get("theta", 0) or 0),
               vega=float(row.get("vega", 0) or 0),
               rho=float(row.get("rho", 0) or 0),
               implied_volatility=float(row.get("implied_volatility", 0) or 0),
               strike_price=float(row.get("strike_price", 0) or 0),
               days_to_expiry=int(row.get("days_to_expiry", 0) or 0),
               option_type=opt_side,
           )
           
           logger.debug(
               f"API 希腊值: Delta={snapshot.delta:.4f} "
               f"Gamma={snapshot.gamma:.4f} "
               f"Theta={snapshot.theta:.4f} "
               f"IV={snapshot.implied_volatility:.2%}"
           )
           return snapshot
           
       except Exception as e:
           logger.error(f"API 获取希腊值异常: {e}")
           return None
   
   def _compute_bs_fallback(self, option_code: str, underlying_price: float) -> Optional[GreeksSnapshot]:
       """使用 BS 模型后备计算希腊值
       
       需要从 option_code 中提取 strike_price 和 expiry 等信息。
       这里尝试解析期权代码中的信息。
       """
       try:
           # 先用 API 获取期权基本信息
           leg = OptionStrategyLeg()
           leg.code = option_code
           leg.quantity = 1
           leg.action = StrategyLegAction.UNKNOWN

           ret, data = self._ctx.get_option_quote([leg])
           if ret != RET_OK or data is None or len(data) == 0:
               return None
           
           row = data.iloc[0]
           
           strike_price = float(row.get("strike_price", 0) or 0)
           days_to_expiry = int(row.get("days_to_expiry", 0) or 0)
           opt_type_str = str(row.get("option_type", ""))
           opt_side = OptionSide.CALL if "CALL" in opt_type_str.upper() else OptionSide.PUT
           market_price = float(row.get("price", 0) or 0)
           
           if strike_price <= 0 or days_to_expiry <= 0:
               return None
           
           S = underlying_price
           K = strike_price
           T = days_to_expiry / 365.0
           r = self._cfg.risk_free_rate
           q = self._cfg.dividend_yield
           
           # 从市场价推算 IV
           sigma = calculate_iv(S, K, T, r, q, market_price, opt_side)
           if sigma <= 0:
               sigma = self._cfg.default_iv
           
           # 计算所有希腊值
           bs = compute_greeks_from_bs(S, K, T, r, q, sigma, opt_side)
           
           now = datetime.datetime.now()
           
           snapshot = GreeksSnapshot(
               timestamp=now,
               option_code=option_code,
               underlying_price=S,
               option_price=bs["price"],
               delta=bs["delta"],
               gamma=bs["gamma"],
               theta=bs["theta"],
               vega=bs["vega"],
               rho=bs["rho"],
               implied_volatility=bs["iv"],
               strike_price=K,
               days_to_expiry=days_to_expiry,
               option_type=opt_side,
           )
           
           logger.debug(
               f"BS 后备希腊值: Delta={snapshot.delta:.4f} "
               f"Gamma={snapshot.gamma:.4f} "
               f"Theta={snapshot.theta:.4f} "
               f"IV(calc)={snapshot.implied_volatility:.2%}"
           )
           return snapshot
           
       except Exception as e:
           logger.error(f"BS 后备计算异常: {e}")
           return None
   
   @property
   def last_greeks(self) -> Optional[GreeksSnapshot]:
       return self._last_greeks
   
   @property
   def last_source(self) -> str:
       return self._last_greeks_source
