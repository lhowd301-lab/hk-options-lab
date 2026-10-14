# -*- coding: utf-8 -*-
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from enum import Enum
from abc import ABC, abstractmethod

class StrategyType(Enum):
    VOLATILITY_BREAKOUT = 'volatility_breakout'
    RSI_MEAN_REVERSION = 'rsi_mean_reversion'
    PUT_CALL_PARITY = 'put_call_parity'
    BOX_SPREAD = 'box_spread'
    HV_IV_SPREAD = 'hv_iv_spread'
    COVERED_CALL = 'covered_call'

class OrderSide(Enum):
    BUY = 'buy'
    SELL = 'sell'

class OptionType(Enum):
    CALL = 'call'
    PUT = 'put'

@dataclass
class Trade:
    trade_id: str
    timestamp: pd.Timestamp
    stock_code: str
    strategy: StrategyType
    side: OrderSide
    option_type: Optional[OptionType]
    strike: float
    quantity: int
    price: float
    premium: float
    underlying_price: float
    iv: Optional[float] = None
    pnl: Optional[float] = None
    bar_index: int = 0
    tags: Dict[str, object] = field(default_factory=dict)

class Strategy(ABC):
    def __init__(self, name: str, strategy_type: StrategyType, params: Dict = None):
        self.name = name
        self.strategy_type = strategy_type
        self.params = params or {}
        self.trades: List[Trade] = []
    @abstractmethod
    def on_bar(self, df: pd.DataFrame, idx: int, option_data: Dict = None) -> Optional[Trade]:
        pass
    def reset(self):
        self.trades = []

class VolatilityBreakout(Strategy):
    def __init__(self, params: Dict = None):
        d = dict(orb_min=30, bp=0.002, min_atr=3.0, min_hv5=25.0, max_hold=6, sl=0.30, tp=0.50)
        if params: d.update(params)
        super().__init__('VolBreakout', StrategyType.VOLATILITY_BREAKOUT, d)
    def on_bar(self, df, idx, od=None):
        if idx < 5: return None
        c = df['close'].iloc[idx]
        h20 = df['high'].iloc[max(0,idx-20):idx+1].max()
        l20 = df['low'].iloc[max(0,idx-20):idx+1].min()
        bp = self.params['bp']
        if c > h20 * (1+bp):
            p = c * 0.02
            return Trade(f'VB{idx}', pd.Timestamp.now(), '', self.strategy_type, OrderSide.BUY, OptionType.CALL, round(c*1.02,1), 1, p, p, c, bar_index=idx)
        if c < l20 * (1-bp):
            p = c * 0.02
            return Trade(f'VB{idx}', pd.Timestamp.now(), '', self.strategy_type, OrderSide.BUY, OptionType.PUT, round(c*0.98,1), 1, p, p, c, bar_index=idx)
        return None

class RSIMeanReversion(Strategy):
    def __init__(self, params: Dict = None):
        d = dict(period=14, os=30, ob=70, min_atr=2.0)
        if params: d.update(params)
        super().__init__('RSIReversion', StrategyType.RSI_MEAN_REVERSION, d)
    def on_bar(self, df, idx, od=None):
        if idx < 16: return None
        close = df['close'].values[:idx+1]
        delta = np.diff(close)
        p = self.params['period']
        g = np.where(delta>0, delta, 0)
        l = np.where(delta<0, -delta, 0)
        ag = np.mean(g[-p:])
        al = max(np.mean(l[-p:]), 0.001)
        rsi = 100 - 100/(1+ag/al)
        c = close[-1]
        if rsi < self.params['os']:
            return Trade(f'RSIL{idx}', pd.Timestamp.now(), '', self.strategy_type, OrderSide.BUY, OptionType.CALL, round(c*0.98,1), 1, c*0.015, c*0.015, c, bar_index=idx)
        if rsi > self.params['ob']:
            return Trade(f'RSIS{idx}', pd.Timestamp.now(), '', self.strategy_type, OrderSide.BUY, OptionType.PUT, round(c*1.02,1), 1, c*0.015, c*0.015, c, bar_index=idx)
        return None

class PutCallParity(Strategy):
    def __init__(self, params: Dict = None):
        d = dict(min_bps=10, rf=0.035, tc=0.001)
        if params: d.update(params)
        super().__init__('PCPArb', StrategyType.PUT_CALL_PARITY, d)
    def on_bar(self, df, idx, od=None):
        if not od or 'chain' not in od: return None
        u = df['close'].iloc[idx]
        for o in od['chain']:
            c, p, k, t = o.get('call_price',0), o.get('put_price',0), o.get('strike',0), o.get('ttm_years',0.05)
            if c<=0 or p<=0 or k<=0: continue
            pv = k * np.exp(-self.params['rf']*t)
            sp = (c+pv-p-u)/u*10000
            if abs(sp) > self.params['min_bps']:
                pm = abs(sp)*u/10000*100
                return Trade(f'PCP{idx}', pd.Timestamp.now(), '', self.strategy_type, OrderSide.BUY if sp<0 else OrderSide.SELL, None, k, 1, pm, pm, u, bar_index=idx)
        return None

class BoxSpread(Strategy):
    def __init__(self, params: Dict = None):
        d = dict(min_bps=5, rf=0.035, max_dist=0.05)
        if params: d.update(params)
        super().__init__('BoxSpread', StrategyType.BOX_SPREAD, d)
    def on_bar(self, df, idx, od=None):
        if not od or 'chain' not in od: return None
        u = df['close'].iloc[idx]
        sk = sorted([o['strike'] for o in od['chain'] if o.get('call_price',0)>0 and o.get('put_price',0)>0])
        for i in range(len(sk)):
            for j in range(i+1, len(sk)):
                k1,k2 = sk[i],sk[j]
                if abs(k2-k1) > u*self.params['max_dist']: continue
                o1 = next(o for o in od['chain'] if o['strike']==k1)
                o2 = next(o for o in od['chain'] if o['strike']==k2)
                c1,p1,c2,p2 = o1['call_price'],o1['put_price'],o2['call_price'],o2['put_price']
                t = o1.get('ttm_years',0.05)
                bp = ((c1-p1)-(c2-p2)-(k2-k1)*np.exp(-self.params['rf']*t))/u*10000
                if abs(bp) > self.params['min_bps']:
                    return Trade(f'BOX{idx}', pd.Timestamp.now(), '', self.strategy_type, OrderSide.BUY, None, k1, 1, abs(bp)*u/100, abs(bp)*u/100, u, bar_index=idx)
        return None

class HVIVSpread(Strategy):
    def __init__(self, params: Dict = None):
        d = dict(ratio_high=1.3, ratio_low=0.7, hv_period=20, min_hv=15.0)
        if params: d.update(params)
        super().__init__('HVIVArb', StrategyType.HV_IV_SPREAD, d)
    def on_bar(self, df, idx, od=None):
        if idx<20 or not od or 'chain' not in od: return None
        c = df['close'].values[:idx+1]
        lr = np.log(c[1:]/c[:-1])
        hv = np.std(lr[-20:])*np.sqrt(252)*100
        if hv<self.params['min_hv']: return None
        u = c[-1]
        for o in od['chain']:
            iv = o.get('iv',0)
            if iv<=0: continue
            r = iv/hv
            if r>self.params['ratio_high']:
                pm = o.get('call_price',0) or o.get('put_price',0)
                if pm>0: return Trade(f'HVIV{idx}', pd.Timestamp.now(), '', self.strategy_type, OrderSide.SELL, None, o['strike'], 1, pm, pm, u, bar_index=idx)
        return None

class CoveredCall(Strategy):
    def __init__(self, params: Dict = None):
        d = dict(otm_pct=0.05, min_prem=1.0)
        if params: d.update(params)
        super().__init__('CvCall', StrategyType.COVERED_CALL, d)
    def on_bar(self, df, idx, od=None):
        if not od or 'chain' not in od: return None
        u = df['close'].iloc[idx]
        for o in od['chain']:
            k = o['strike']
            if abs(k-u*(1+self.params['otm_pct']))/u<0.02:
                cp = o.get('call_price',0)
                if cp>0 and cp/u*100 >= self.params['min_prem']:
                    return Trade(f'CC{idx}', pd.Timestamp.now(), '', self.strategy_type, OrderSide.SELL, OptionType.CALL, k, 1, cp, cp, u, bar_index=idx)
        return None
