# -*- coding: utf-8 -*-
import numpy as np
from scipy.stats import norm
from typing import Dict, List, Optional

class OptionPricer:
    @staticmethod
    def bs_price(S: float, K: float, T: float, r: float, sigma: float, opt_type: str = 'call') -> float:
        if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
            return 0
        d1 = (np.log(S/K) + (r + sigma**2/2)*T) / (sigma*np.sqrt(T))
        d2 = d1 - sigma*np.sqrt(T)
        if opt_type == 'call':
            return S*norm.cdf(d1) - K*np.exp(-r*T)*norm.cdf(d2)
        else:
            return K*np.exp(-r*T)*norm.cdf(-d2) - S*norm.cdf(-d1)

    @staticmethod
    def bs_delta(S: float, K: float, T: float, r: float, sigma: float, opt_type: str = 'call') -> float:
        if T <= 0 or sigma <= 0: return 0
        d1 = (np.log(S/K) + (r + sigma**2/2)*T) / (sigma*np.sqrt(T))
        if opt_type == 'call':
            return norm.cdf(d1)
        else:
            return norm.cdf(d1) - 1

    @staticmethod
    def implied_vol(S: float, K: float, T: float, r: float, market_price: float, opt_type: str = 'call') -> float:
        from scipy.optimize import brentq
        def f(sigma):
            return OptionPricer.bs_price(S, K, T, r, sigma, opt_type) - market_price
        try:
            return brentq(f, 0.001, 3.0)
        except:
            return 0.2

def simulate_option_chain(underlying: float, expiry_days: int = 30,
                           strikes: Optional[List[float]] = None,
                           hv: float = 0.30, rf: float = 0.035,
                           spread_pct: float = 0.02) -> List[Dict]:
    T = expiry_days / 365.0
    if not strikes:
        step = round(underlying * 0.02, 1)
        num = 10
        strikes = [underlying * (1 + (i-num//2)*0.02) for i in range(num)]
        strikes = sorted(set(round(s, 1) for s in strikes))
    chain = []
    for K in strikes:
        c = OptionPricer.bs_price(underlying, K, T, rf, hv, 'call')
        p = OptionPricer.bs_price(underlying, K, T, rf, hv, 'put')
        spread = c * spread_pct
        chain.append(dict(
            strike=round(K, 1), call_price=round(max(c - spread/2, 0.01), 2),
            put_price=round(max(p - spread/2, 0.01), 2),
            call_ask=round(c + spread/2, 2), put_ask=round(p + spread/2, 2),
            iv=round(hv, 3), ttm_years=round(T, 4), delta_c=round(OptionPricer.bs_delta(underlying, K, T, rf, hv, 'call'), 3),
            delta_p=round(OptionPricer.bs_delta(underlying, K, T, rf, hv, 'put'), 3)
        ))
    return chain
