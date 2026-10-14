# -*- coding: utf-8 -*-
import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional
from datetime import datetime
from .strategies import Strategy, Trade, OrderSide, StrategyType, OptionType

class BacktestEngine:
    def __init__(self, name: str = 'Backtest', capital: float = 100000.0, comm_pct: float = 0.001):
        self.name = name
        self.capital = capital
        self.comm_pct = comm_pct
        self.strategies: List[Strategy] = []
        self.exit_lookahead = 3
        self.trades: List[Trade] = []
        self.equity: List[Dict] = []

    def add_strategy(self, s: Strategy):
        self.strategies.append(s)

    def run(self, price_df: pd.DataFrame, opt_data: Optional[Dict] = None) -> Dict[str, Any]:
        self.trades.clear()
        self.equity.clear()
        for s in self.strategies:
            s.reset()
        cash = self.capital
        for idx in range(len(price_df)):
            od = opt_data.get(idx) if isinstance(opt_data, dict) else opt_data
            for s in self.strategies:
                trade = s.on_bar(price_df, idx, od)
                if trade:
                    trade.stock_code = str(getattr(price_df, 'attrs', {}).get('code', ''))
                    self.trades.append(trade)
            self.equity.append({'bar': idx, 'cash': cash, 'trades': len(self.trades)})
        self._simulate_pnl(price_df, self.exit_lookahead)
        results = self._calc_results()
        results['strategies'] = {s.name: len(s.trades) for s in self.strategies}
        return results

    def _simulate_pnl(self, df, lookahead=3):
        from ..data.options import OptionPricer
        prices = df['close'].values.astype(float)
        for t in self.trades:
            entry_idx = getattr(t, 'bar_index', 0)
            exit_idx = min(entry_idx + lookahead, len(prices) - 1)
            if exit_idx <= entry_idx: exit_idx = entry_idx
            S_entry = t.underlying_price; S_exit = prices[exit_idx]
            K = t.strike; T = 30/365.0; sigma = 0.30; r = 0.035
            try:
                if t.option_type == OptionType.CALL:
                    eb = OptionPricer.bs_price(S_entry, K, T, r, sigma, 'call')
                    ex = OptionPricer.bs_price(S_exit, K, T, r, sigma, 'call')
                elif t.option_type == OptionType.PUT:
                    eb = OptionPricer.bs_price(S_entry, K, T, r, sigma, 'put')
                    ex = OptionPricer.bs_price(S_exit, K, T, r, sigma, 'put')
                else:
                    t.pnl = -t.premium if t.side == OrderSide.BUY else t.premium; continue
                if eb < 0.01:
                    ret = (S_exit - S_entry) / S_entry; lev = 20.0
                    if t.option_type == OptionType.CALL: est = t.premium * ret * lev
                    else: est = t.premium * (-ret) * lev
                    if t.side == OrderSide.SELL: est = -est
                    t.pnl = round(est, 2)
                else:
                    pnl = ex - eb
                    if t.side == OrderSide.SELL: pnl = -pnl
                    t.pnl = round(pnl, 2)
            except:
                t.pnl = round(-t.premium if t.side == OrderSide.BUY else t.premium, 2)

    def _calc_results(self) -> Dict:
        total_pnl = sum(getattr(t, chr(112)+chr(110)+chr(108), -t.premium*(1+self.comm_pct) if t.side==OrderSide.BUY else t.premium*(1-self.comm_pct)) for t in self.trades)
        n = len(self.trades)
        wins = sum(1 for t in self.trades if getattr(t,chr(112)+chr(110)+chr(108),0) and getattr(t,chr(112)+chr(110)+chr(108),0) > 0)
        return dict(
            engine=self.name, capital=self.capital, final=self.capital+total_pnl,
            pnl=round(total_pnl,2), pnl_pct=round(total_pnl/self.capital*100,2),
            trades=n, wins=wins, losses=n-wins,
            win_rate=round(wins/max(n,1)*100,2),
            premium=round(sum(t.premium for t in self.trades),2),
        )
