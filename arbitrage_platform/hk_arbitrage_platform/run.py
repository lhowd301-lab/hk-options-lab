# -*- coding: utf-8 -*-
"""
HK Options Arbitrage Platform - CLI Entry Point
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
import pandas as pd
import numpy as np
from datetime import datetime

from hk_arbitrage_platform.backtest.engine import BacktestEngine
from hk_arbitrage_platform.backtest.strategies import (
    VolatilityBreakout, RSIMeanReversion, PutCallParity,
    BoxSpread, HVIVSpread, CoveredCall
)
from hk_arbitrage_platform.backtest.metrics import Metrics
from hk_arbitrage_platform.data.fetcher import DataFetcher
from hk_arbitrage_platform.data.options import simulate_option_chain
from hk_arbitrage_platform.analysis.reporter import ReportGenerator


STRATEGY_MAP = {
    '1': ('Volatility Breakout (ORB)', VolatilityBreakout),
    '2': ('RSI Mean Reversion', RSIMeanReversion),
    '3': ('Put-Call Parity Arbitrage', PutCallParity),
    '4': ('Box Spread Arbitrage', BoxSpread),
    '5': ('HV-IV Volatility Arbitrage', HVIVSpread),
    '6': ('Covered Call', CoveredCall),
}

def main():
    print('=' * 60)
    print('  HK Options Arbitrage Backtesting Platform')
    print('  Data from QQ Finance + Futu API')
    print('=' * 60)

    # Select strategy
    print('\nSelect Strategy:')
    for k, (name, _) in STRATEGY_MAP.items():
        print(f'  [{k}] {name}')
    choice = input('\nStrategy (1-6, default=1): ').strip() or '1'
    if choice not in STRATEGY_MAP:
        print(f'Invalid choice: {choice}')
        return
    strat_name, strat_cls = STRATEGY_MAP[choice]
    print(f'  Selected: {strat_name}')

    # Select stocks
    print('\nAvailable HK Stocks:')
    codes_list = list(DataFetcher.HK_CODES.items())
    for i, (code, name_en) in enumerate(codes_list):
        name_cn = DataFetcher.HK_NAMES.get(code, '')
        print(f'  [{i+1}] {code} - {name_cn} ({name_en})')
    stock_input = input('\nSelect stocks (comma separated, default=1): ').strip()
    if not stock_input:
        selected_codes = ['00700']
    else:
        selected_codes = [codes_list[int(i)-1][0] for i in stock_input.split(',') if i.strip().isdigit()]
    print(f'  Selected: {", ".join(selected_codes)}')

    capital = float(input('Initial capital (default=100000): ').strip() or '100000')

    print('\n' + '-' * 60)
    print('Fetching market data...')
    print('-' * 60)

    # Fetch data
    all_data = {}
    for code in selected_codes:
        df = DataFetcher.fetch_qq(code, 150)
        if df is not None and len(df) > 10:
            all_data[code] = df
            indicator = DataFetcher.calc_indicators(df)
            print(f'  {code}: {len(df)} days, latest={indicator["price"]}, ATR%={indicator["atr_pct"]}%, HV5={indicator["hv5"]}%')

    if not all_data:
        print('ERROR: No data fetched!')
        return

    print('\n' + '-' * 60)
    print('Running backtest...')
    print('-' * 60)

    # Run backtest for each stock
    all_trades = []
    all_results = {}

    for code, df in all_data.items():
        name = df.attrs.get('name', code)
        engine = BacktestEngine(name=f'{code}_{strat_name}', capital=capital)
        strategy = strat_cls()
        engine.add_strategy(strategy)

        # Generate option chain for each bar
        opt_data = {}
        for idx in range(len(df)):
            u = df['close'].iloc[idx]
            hv = 0.30
            try:
                c = df['close'].values.astype(float)
                lr = np.log(c[1:]/c[:-1])
                hv = float(np.std(lr[-20:])*np.sqrt(252)) if len(lr)>=20 else 0.30
            except:
                pass
            opt_data[idx] = {'chain': simulate_option_chain(u, 30, hv=hv)}

        result = engine.run(df, opt_data)
        result['stock_code'] = code
        result['stock_name'] = name
        all_results[code] = result
        all_trades.extend(engine.trades)

        print(f'  {name} ({code}): {result["trades"]} trades, P&L=${result["pnl"]:.2f} ({result["pnl_pct"]:.2f}%)')

    # Metrics
    metrics = Metrics.compute(all_trades, capital, [])

    print('\n' + '=' * 60)
    print('  RESULTS SUMMARY')
    print('=' * 60)
    print(f'  Strategy:     {strat_name}')
    print(f'  Stocks:       {len(all_data)}')
    print(f'  Total Trades: {metrics["trades"]}')
    print(f'  Win Rate:     {metrics["win_rate"]:.1f}%')
    print(f'  Total P&L:    ${metrics["pnl"]:.2f} ({metrics["pnl_pct"]:.2f}%)')
    print(f'  Profit Factor:{metrics["profit_factor"]:.2f}')
    print(f'  Sharpe Ratio: {metrics["sharpe"]:.3f}')
    print(f'  Max DD:       {metrics["max_dd"]:.2f}%')
    print(f'  Final Capital:${metrics["final"]:.2f}')
    print('=' * 60)

    # Save report
    report_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              'hk_arbitrage_platform', 'reports')
    os.makedirs(report_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_path = os.path.join(report_dir, f'backtest_report_{timestamp}.html')
    ReportGenerator.save_report(metrics, all_trades, report_path)

    print(f'\nReport saved: {report_path}')
    print('Done!')


if __name__ == '__main__':
    main()
