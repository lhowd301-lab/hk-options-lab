# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, request, jsonify, send_file
import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta
import base64, io, traceback

from ..backtest.engine import BacktestEngine
from ..backtest.strategies import VolatilityBreakout, RSIMeanReversion, PutCallParity, BoxSpread, HVIVSpread, CoveredCall, Trade, OrderSide
from ..backtest.metrics import Metrics
from ..data.fetcher import DataFetcher
from ..data.options import OptionPricer, simulate_option_chain
from ..realtime.monitor import Monitor
from ..realtime.datafeed import DataFeed
from ..realtime.executor import Executor

# Global realtime monitor state
_monitor = None
_executor = None

def get_monitor():
    global _monitor, _executor
    if _monitor is None:
        feed = DataFeed()
        _monitor = Monitor(feed)
        _executor = Executor(_monitor)
        _monitor.datafeed.on_data(lambda c, d: _executor.update_positions({c: d.get("price", 0)}))
    return _monitor, _executor

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'hk-arb-platform'

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/api/backtest', methods=['POST'])
    def run_backtest():
        try:
            data = request.get_json() or {}
            codes = data.get('codes', ['00700'])
            strategy_name = data.get('strategy', 'volatility_breakout')
            capital = float(data.get('capital', 100000))
            days = int(data.get('days', 150))
            interval = data.get('interval', 'daily')

            # Fetch data
            all_data = {}
            for code in codes:
                df = DataFetcher.fetch_qq(code, days)
                if df is not None:
                    all_data[code] = df

            if not all_data:
                return jsonify({'error': 'No data fetched'}), 400

            # Run backtest for each stock
            all_results = {}
            all_trades = []

            lookahead = 3
            interval_min = 0
            if interval != 'daily':
                interval_min = int(interval.replace('min', ''))
                lookahead = {15:12, 30:6, 60:3}.get(interval_min, 12)

            for code, df in all_data.items():
                if interval != 'daily':
                    df = DataFetcher.generate_intraday(df, interval_min)
                engine = BacktestEngine(name=f'Backtest_{code}', capital=capital)
                engine.exit_lookahead = lookahead
                strat_map = {
                    'volatility_breakout': VolatilityBreakout(),
                    'rsi_mean_reversion': RSIMeanReversion(),
                    'put_call_parity': PutCallParity(),
                    'box_spread': BoxSpread(),
                    'hv_iv_spread': HVIVSpread(),
                    'covered_call': CoveredCall(),
                }
                s = strat_map.get(strategy_name)
                if not s:
                    return jsonify({'error': f'Unknown strategy: {strategy_name}'}), 400

                engine.add_strategy(s)

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
                result['stock_code'] = str(code)
                result['stock_name'] = str(df.attrs.get('name', code))
                # Add individual trade data
                trade_list = []
                equity_curve = []
                cum = 0
                for t in engine.trades:
                    trade_pnl = float(t.pnl) if t.pnl is not None else (-float(t.premium) if t.side == OrderSide.BUY else float(t.premium))
                    cum += trade_pnl
                    trade_list.append({
                        'id': t.trade_id, 'side': t.side.name,
                        'type': t.option_type.name if t.option_type else 'both',
                        'strike': t.strike, 'premium': round(t.premium, 2),
                        'underlying': round(t.underlying_price, 2),
                        'pnl': round(trade_pnl, 2), 'cum': round(cum, 2),
                        'is_win': bool(trade_pnl > 0)
                    })
                    equity_curve.append(round(cum, 2))
                result['trade_list'] = trade_list
                result['equity'] = equity_curve
                all_results[code] = result
                all_trades.extend(engine.trades)

            # Aggregate
            total_pnl = sum(r['pnl'] for r in all_results.values())
            total_trades = sum(r['trades'] for r in all_results.values())
            total_wins = sum(r['wins'] for r in all_results.values())

            return jsonify({
                'results': all_results,
                'aggregate': {
                    'stocks': len(all_results),
                    'trades': total_trades,
                    'pnl': round(total_pnl, 2),
                    'pnl_pct': round(total_pnl / (capital * len(all_results)) * 100, 2),
                    'win_rate': round(total_wins/max(total_trades,1)*100, 2),
                    'capital': capital,
                },
                'n_trades': len(all_trades)
            })

        except Exception as e:
            return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500

    @app.route('/api/stocks')
    def list_stocks():
        return jsonify(DataFetcher.HK_CODES)

    # ── Real-time Monitoring Routes ──
    @app.route('/realtime')
    def realtime_page():
        return render_template('realtime.html')

    @app.route('/api/realtime/status')
    def realtime_status():
        mon, exe = get_monitor()
        state = mon.get_state()
        state['executor'] = exe.get_state()
        return jsonify(state)

    @app.route('/api/realtime/start', methods=['POST'])
    def realtime_start():
        data = request.get_json() or {}
        mon, exe = get_monitor()
        codes = data.get('codes', ['00700'])
        strategy = data.get('strategy', 'rsi_mean_reversion')
        interval = int(data.get('interval', 30))
        mon.configure(codes, strategy, interval)
        mon.datafeed.on_data(lambda c, d: exe.update_positions({c: d.get('price', 0)}))
        mon.start()
        return jsonify({'status': 'ok'})

    @app.route('/api/realtime/stop', methods=['POST'])
    def realtime_stop():
        mon, _ = get_monitor()
        mon.stop()
        return jsonify({'status': 'stopped'})

    @app.route('/api/realtime/auto', methods=['POST'])
    def realtime_auto():
        data = request.get_json() or {}
        _, exe = get_monitor()
        exe.set_auto_trade(data.get('enabled', False))
        return jsonify({'status': 'ok', 'auto_trade': exe.auto_trade})

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='127.0.0.1', port=5000, debug=True)
