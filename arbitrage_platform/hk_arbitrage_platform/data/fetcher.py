# -*- coding: utf-8 -*-
import numpy as np
import pandas as pd
import requests
import time
from typing import Dict, Optional, List
from datetime import datetime, timedelta

HK_CODES = {
    '00700':'Tencent','01810':'Xiaomi','00981':'SMIC','00992':'Lenovo',
    '09888':'Baidu','09626':'Bilibili','01024':'Kuaishou','09999':'NetEase',
    '09988':'Alibaba','09618':'JD','02382':'SunnyOptical','09961':'Trip',
}
HK_NAMES = {
    '00700':'腾讯控股','01810':'小米集团','00981':'中芯国际','00992':'联想集团',
    '09888':'百度集团','09626':'哔哩哔哩','01024':'快手','09999':'网易',
    '09988':'阿里巴巴','09618':'京东集团','02382':'舜宇光学科技','09961':'携程集团',
}

class DataFetcher:
    @staticmethod
    def fetch_qq(code: str, days: int = 150) -> Optional[pd.DataFrame]:
        url = f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=hk{code},day,,,{days},qfq'
        for _ in range(3):
            try:
                r = requests.get(url, timeout=15)
                data = r.json()
                dd = data['data'][f'hk{code}']['day']
                dd = [row[:6] for row in dd]
                df = pd.DataFrame(dd, columns=['date','open','close','high','low','volume'])
                for c in ['open','close','high','low']:
                    df[c] = df[c].astype(float)
                df['volume'] = df['volume'].astype(float)
                df['date'] = pd.to_datetime(df['date'])
                df.attrs['code'] = code
                df.attrs['name'] = HK_NAMES.get(code, code)
                return df
            except:
                time.sleep(1)
        return None

    @staticmethod
    def fetch_all_qq(days: int = 150) -> Dict[str, pd.DataFrame]:
        result = {}
        for code in HK_CODES:
            df = DataFetcher.fetch_qq(code, days)
            if df is not None and len(df) > 10:
                result[code] = df
                print(f'  {code} {HK_NAMES.get(code,"")}: {len(df)} days')
            time.sleep(0.5)
        print(f'Got {len(result)}/{len(HK_CODES)} stocks')
        return result

    @staticmethod
    def calc_indicators(df: pd.DataFrame) -> pd.DataFrame:
        close = df['close'].values.astype(float)
        high = df['high'].values.astype(float)
        low = df['low'].values.astype(float)
        vol = df['volume'].values.astype(float)
        # ATR
        tr = [max(high[i]-low[i], abs(high[i]-close[i-1]), abs(low[i]-close[i-1])) for i in range(1,len(close))]
        atr5 = np.mean(tr[-5:]) if len(tr)>=5 else np.mean(tr) if tr else 0
        atr_pct = atr5/close[-1]*100 if close[-1]>0 else 0
        # HV
        lr = np.log(close[1:]/close[:-1])
        hv5 = np.std(lr[-5:])*np.sqrt(252)*100 if len(lr)>=5 else 0
        hv20 = np.std(lr[-20:])*np.sqrt(252)*100 if len(lr)>=20 else 0
        hvt = 'up' if hv5>hv20*1.05 else ('down' if hv5<hv20*0.95 else 'flat')
        # Bollinger
        if len(close)>=20:
            bm, bs = np.mean(close[-20:]), np.std(close[-20:])
            bp = (close[-1]-(bm-2*bs))/(4*bs)*100
            bsig = 'lower' if bp<25 else ('upper' if bp>75 else 'mid')
        else:
            bp, bsig = 50, 'mid'
        # RSI
        delta = np.diff(close)
        g = np.where(delta>0, delta, 0)
        l = np.where(delta<0, -delta, 0)
        ag, al = np.mean(g[-14:]), max(np.mean(l[-14:]),0.001)
        rsi = 100-100/(1+ag/al)
        return dict(code=df.attrs.get('code',''), name=HK_NAMES.get(df.attrs.get('code',''),''),
                    price=round(close[-1],2), atr_pct=round(atr_pct,2),
                    hv5=round(hv5,2), hv20=round(hv20,2), hv_trend=hvt,
                    bb_pos=round(bp,1), bb_sig=bsig,
                    rsi=round(rsi,1), volume=float(vol[-1]))

    @staticmethod
    def fetch_futu_realtime(code: str):
        try:
            from futu import OpenQuoteContext, RET_OK
            ctx = OpenQuoteContext(host='127.0.0.1', port=11111)
            ret, data = ctx.get_stock_basicinfo('HK', code)
            ctx.close()
            if ret == RET_OK:
                return data
        except:
            pass
        return None

    @staticmethod
    def generate_intraday(df, interval_min=15):
        import numpy as np
        n_bars = {5:66, 15:22, 30:11, 60:6}.get(interval_min, 22)
        all_bars = []
        for day_idx in range(len(df)):
            day = df.iloc[day_idx]
            o, h, l, c = float(day['open']), float(day['high']), float(day['low']), float(day['close'])
            date = day['date']
            rng = max(h-l, 0.01)
            np.random.seed(abs(hash(str(date))) % (2**31-1))
            t = np.linspace(0, 1, n_bars+1)
            path = o + (c-o)*t
            vol = 1 - 0.5*np.sin(np.pi*t)
            noise = np.random.randn(n_bars+1) * rng * 0.08 * vol
            path = np.clip(path + noise, l, h)
            path[0], path[-1] = o, c
            for i in range(n_bars):
                op, cp = path[i], path[i+1]
                bh = min(max(op,cp) + np.random.rand()*(h-max(op,cp))*0.3, h+0.01)
                bl = max(min(op,cp) - np.random.rand()*(min(op,cp)-l)*0.3, l-0.01)
                mins = 570 + interval_min*i
                bar_time = pd.Timestamp(date.year, date.month, date.day, mins//60, mins%60)
                all_bars.append({'time':bar_time, 'open':round(op,2), 'high':round(bh,2), 'low':round(bl,2), 'close':round(cp,2), 'volume':float(day['volume'])//max(n_bars,1), 'date':date})
        result = pd.DataFrame(all_bars)
        result.attrs = df.attrs
        return result
