"""Black-Scholes 期权定价与希腊值计算（后备引擎）"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
from scipy.stats import norm

from .models import GreeksSnapshot, OptionSide


def _validate_params(S: float, K: float, T: float, sigma: float, r: float, q: float) -> None:
   if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
       raise ValueError(f"Invalid BS params: S={S}, K={K}, T={T}, sigma={sigma}")


def d1(S: float, K: float, T: float, sigma: float, r: float, q: float) -> float:
   return (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))


def d2(S: float, K: float, T: float, sigma: float, r: float, q: float) -> float:
   return d1(S, K, T, sigma, r, q) - sigma * math.sqrt(T)


def bs_price(S: float, K: float, T: float, sigma: float, r: float, q: float, opt_type: OptionSide) -> float:
   """Black-Scholes 期权价格"""
   _validate_params(S, K, T, sigma, r, q)
   d1_val = d1(S, K, T, sigma, r, q)
   d2_val = d2(S, K, T, sigma, r, q)
   
   if opt_type == OptionSide.CALL:
       return S * math.exp(-q * T) * norm.cdf(d1_val) - K * math.exp(-r * T) * norm.cdf(d2_val)
   else:
       return K * math.exp(-r * T) * norm.cdf(-d2_val) - S * math.exp(-q * T) * norm.cdf(-d1_val)


def bs_delta(S: float, K: float, T: float, sigma: float, r: float, q: float, opt_type: OptionSide) -> float:
   """Delta"""
   _validate_params(S, K, T, sigma, r, q)
   d1_val = d1(S, K, T, sigma, r, q)
   if opt_type == OptionSide.CALL:
       return math.exp(-q * T) * norm.cdf(d1_val)
   else:
       return math.exp(-q * T) * (norm.cdf(d1_val) - 1)


def bs_gamma(S: float, K: float, T: float, sigma: float, r: float, q: float, opt_type: Optional[OptionSide] = None) -> float:
   """Gamma (CALL 和 PUT 相同)"""
   _validate_params(S, K, T, sigma, r, q)
   d1_val = d1(S, K, T, sigma, r, q)
   return math.exp(-q * T) * norm.pdf(d1_val) / (S * sigma * math.sqrt(T))


def bs_theta(S: float, K: float, T: float, sigma: float, r: float, q: float, opt_type: OptionSide) -> float:
   """Theta (每日, 已除以 365)"""
   _validate_params(S, K, T, sigma, r, q)
   d1_val = d1(S, K, T, sigma, r, q)
   d2_val = d2(S, K, T, sigma, r, q)
   pdf_d1 = norm.pdf(d1_val)
   
   term1 = -S * sigma * math.exp(-q * T) * pdf_d1 / (2 * math.sqrt(T))
   
   if opt_type == OptionSide.CALL:
       term2 = -r * K * math.exp(-r * T) * norm.cdf(d2_val)
       term3 = q * S * math.exp(-q * T) * norm.cdf(d1_val)
   else:
       term2 = r * K * math.exp(-r * T) * norm.cdf(-d2_val)
       term3 = -q * S * math.exp(-q * T) * norm.cdf(-d1_val)
   
   return (term1 + term2 + term3) / 365.0


def bs_vega(S: float, K: float, T: float, sigma: float, r: float, q: float, opt_type: Optional[OptionSide] = None) -> float:
   """Vega (表示 1% IV 变动对应的价格变动)"""
   _validate_params(S, K, T, sigma, r, q)
   d1_val = d1(S, K, T, sigma, r, q)
   return S * math.sqrt(T) * math.exp(-q * T) * norm.pdf(d1_val) / 100.0


def bs_rho(S: float, K: float, T: float, sigma: float, r: float, q: float, opt_type: OptionSide) -> float:
   """Rho (表示 1% 利率变动对应的价格变动)"""
   _validate_params(S, K, T, sigma, r, q)
   d2_val = d2(S, K, T, sigma, r, q)
   if opt_type == OptionSide.CALL:
       return K * T * math.exp(-r * T) * norm.cdf(d2_val) / 100.0
   else:
       return -K * T * math.exp(-r * T) * norm.cdf(-d2_val) / 100.0


def calculate_iv(
   S: float, K: float, T: float, r: float, q: float,
   market_price: float, opt_type: OptionSide,
  max_iter: int = 100, tol: float = 1e-6
) -> float:
   """Newton-Raphson 求解隐含波动率"""
   if market_price <= 0:
       return 0.0
   
   intrinsic = max(0, (S - K) if opt_type == OptionSide.CALL else (K - S))
   if abs(market_price - intrinsic) < 0.001:
       return 0.0  # 深度实值，IV 无意义
   
   sigma = 0.3  # 初始猜测
   for _ in range(max_iter):
       price = bs_price(S, K, T, sigma, r, q, opt_type)
       diff = price - market_price
       if abs(diff) < tol:
           return sigma
       vega_val = bs_vega(S, K, T, sigma, r, q, opt_type) * 100  # 还原为 1% IV 变动
       if abs(vega_val) < 1e-10:
           break
       sigma -= diff / vega_val
       sigma = max(0.005, min(5.0, sigma))  # 边界约束
   
   return sigma


def compute_greeks_from_bs(
   S: float, K: float, T: float, r: float, q: float,
   sigma: float, opt_type: OptionSide
) -> dict:
   """一次性计算所有 BS 希腊值"""
   g = {
       "delta": bs_delta(S, K, T, sigma, r, q, opt_type),
       "gamma": bs_gamma(S, K, T, sigma, r, q, opt_type),
       "theta": bs_theta(S, K, T, sigma, r, q, opt_type),
       "vega": bs_vega(S, K, T, sigma, r, q, opt_type),
       "rho": bs_rho(S, K, T, sigma, r, q, opt_type),
       "iv": sigma,
       "price": bs_price(S, K, T, sigma, r, q, opt_type),
   }
   return g
