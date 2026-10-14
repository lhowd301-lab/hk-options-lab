# -*- coding: utf-8 -*-
import numpy as np
from typing import List, Dict
from .strategies import Trade, OrderSide

class Metrics:
    @staticmethod
    def compute(trades: List[Trade], capital: float, equity: List[Dict]) -> Dict:
        if not trades:
            return dict(error='no trades')
        pnls = []
        for t in trades:
            v = t.price * (1 if t.side==OrderSide.SELL else -1)
            pnls.append(v)
        arr = np.array(pnls)
        pos = arr[arr>0]
        neg = arr[arr<0]
        total = float(arr.sum())
        wr = len(pos)/max(len(arr),1)*100
        avg_w = float(pos.mean()) if len(pos)>0 else 0
        avg_l = float(abs(neg.mean())) if len(neg)>0 else 0
        pf = float(pos.sum()/max(abs(neg.sum()),1e-10)) if len(neg)>0 else float('inf')
        sr = float(arr.mean()/max(arr.std(),1e-10)*np.sqrt(252)) if len(arr)>1 else 0
        cum = np.cumsum(arr)
        peak = np.maximum.accumulate(cum)
        dd = float(((peak-cum)/max(peak.max(),1)).max()*100) if len(cum)>0 else 0
        return dict(pnl=round(total,2), pnl_pct=round(total/capital*100,2),
                    trades=len(trades), win_rate=round(wr,2),
                    avg_win=round(avg_w,2), avg_loss=round(avg_l,2),
                    profit_factor=round(pf,2), sharpe=round(sr,3),
                    max_dd=round(dd,2), final=round(capital+total,2))
