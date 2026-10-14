"""
智能模拟交易系统 - Web服务器

启动: python -m sim_trader.web_server
访问: http://localhost:5000
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import json
import threading
import logging
from typing import Optional

try:
    from flask import Flask, jsonify, render_template, request
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "flask"])
    from flask import Flask, jsonify, render_template, request

from datetime import datetime
from .config import CONFIG as cfg
from .simulation_account import SimulationAccount
from .strategy import TradingStrategy
from .connector import FutuConnector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("web")

# === 全局状态 ===
account = SimulationAccount()
strategy = TradingStrategy(account)
connector = FutuConnector()

state_lock = threading.Lock()

# 最新状态缓存
last_price: float = 0.0
last_prev_close: float = 0.0
conn_status: str = "未连接"
market_status: str = "未知"
last_update: str = "--:--:--"


def price_callback(code: str, price: float):
    """富途推送回调"""
    with state_lock:
        global last_price, last_update
        last_price = price
        last_update = datetime.now().strftime("%H:%M:%S")
        strategy.feed_price(price)


def background_poller():
    """后台轮询线程"""
    global conn_status, market_status, last_price, last_update, last_prev_close

    logger.info("Web服务器: 正在连接富途API...")
    connected = connector.connect()

    if connected:
        conn_status = "已连接"
        quote = connector.get_current_quote()
        if quote:
            last_price = quote
            last_update = datetime.now().strftime("%H:%M:%S")

        kline_prices = connector.get_today_1min_klines()
        for p in kline_prices:
            strategy.feed_price(p)

        sub_ok = connector.subscribe(price_callback)
        if sub_ok:
            market_status = connector.get_market_state()
        else:
            conn_status = "订阅失败"
    else:
        conn_status = "未连接"

    logger.info("网页状态: %s, 市场: %s", conn_status, market_status)

    while True:
        try:
            time.sleep(cfg.refresh_interval)
            if connector.connected:
                quote = connector.get_current_quote()
                with state_lock:
                    if quote and quote > 0:
                        last_price = quote
                        last_update = datetime.now().strftime("%H:%M:%S")
                        strategy.feed_price(quote)
        except Exception:
            pass


def get_status_dict() -> dict:
    """获取当前状态"""
    with state_lock:
        price = last_price or 0
        avg = strategy.avg_price
        stop_loss = strategy.stop_loss_price
        acct = account
        mkt_val = acct.market_value(price) if price > 0 else 0
        total = acct.total_assets(price) if price > 0 else acct.cash
        pnl_val = acct.pnl(price) if price > 0 else 0

        diff = 0
        diff_pct = 0
        if price > 0 and avg and avg > 0:
            diff = round(price - avg, 4)
            diff_pct = round(diff / avg * 100, 2)

        change = 0
        change_pct = 0
        if price > 0 and last_prev_close > 0:
            change = round(price - last_prev_close, 4)
            change_pct = round(change / last_prev_close * 100, 2)

        return {
            # 行情
            "price": round(price, 4) if price > 0 else None,
            "price_str": f"{price:.4f}" if price > 0 else "--",
            "change": round(change, 4),
            "change_pct": round(change_pct, 2),
            "change_str": f"{change:+.4f} ({change_pct:+.2f}%)" if last_prev_close > 0 else "--",
            "avg_price": round(avg, 4) if avg else None,
            "avg_price_str": f"{avg:.4f}" if avg else "收集中...",
            "stop_loss": round(stop_loss, 4) if stop_loss else None,
            "stop_loss_str": f"{stop_loss:.4f}" if stop_loss else "N/A",
            "diff": diff,
            "diff_pct": diff_pct,
            "diff_str": f"{diff:+.4f} ({diff_pct:+.2f}%)" if avg else "--",
            "in_avg_period": account.is_avg_period,
            "avg_collected": len(strategy.prices_30min),
            "avg_target": cfg.avg_minutes,
            # 账户
            "cash": round(acct.cash, 2),
            "cash_str": f"{acct.cash:,.2f}",
            "position": acct.position,
            "avg_cost": round(acct.avg_cost, 4) if acct.avg_cost > 0 else None,
            "market_value": round(mkt_val, 2),
            "market_value_str": f"{mkt_val:,.2f}",
            "total_assets": round(total, 2),
            "total_assets_str": f"{total:,.2f}",
            "init_cash": acct.initial_cash,
            "pnl": round(pnl_val, 2),
            "pnl_str": f"{pnl_val:+,.2f}",
            "pnl_pct": round(acct.pnl_pct(price) if price > 0 else 0, 2),
            "pnl_pct_str": f"{acct.pnl_pct(price):+.2f}%" if price > 0 else "0.00%",
            # 策略
            "signal": strategy.get_signal_text(),
            "avg_set_time": acct.avg_set_time or "",
            "trade_count": len(acct.trade_log),
            # 连接
            "conn_status": conn_status,
            "market_status": market_status,
            "last_update": last_update,
            "stock_code": cfg.stock_code,
            "stock_name": cfg.stock_name,
            "refresh_interval": cfg.refresh_interval,
        }


# === Flask 路由 ===

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("dashboard.html", cfg=cfg)


@app.route("/api/status")
def api_status():
    return jsonify(get_status_dict())


@app.route("/api/config", methods=["POST"])
def api_config():
    global conn_status
    data = request.get_json(force=True)
    if "cash" in data:
        new_cash = float(data["cash"])
        if new_cash > 0:
            with state_lock:
                cfg.initial_cash = new_cash
    if "code" in data:
        new_code = str(data["code"]).strip()
        if new_code:
            with state_lock:
                cfg.stock_code = new_code
    if "futu_host" in data:
        cfg.futu_host = str(data["futu_host"])
    if "futu_port" in data:
        cfg.futu_quote_port = int(data["futu_port"])
    return jsonify({"ok": True})


@app.route("/api/trades")
def api_trades():
    with state_lock:
        trades = []
        for i, t in enumerate(account.trade_log[-50:], 1):
            trades.append({
                "no": i,
                "time": t.time,
                "action": t.action,
                "shares": t.shares,
                "price": round(t.price, 4),
                "amount": round(t.amount, 2),
                "cash_after": round(t.cash_after, 2),
                "pos_after": t.pos_after,
            })
    return jsonify(trades)


@app.route("/api/action/connect", methods=["POST"])
def api_reconnect():
    global conn_status, market_status
    if not connector.connected:
        connected = connector.connect()
        if connected:
            conn_status = "已连接"
            market_status = connector.get_market_state()
            quote = connector.get_current_quote()
            if quote:
                with state_lock:
                    global last_price
                    last_price = quote
            return jsonify({"ok": True, "status": "已连接"})
        else:
            return jsonify({"ok": False, "status": "连接失败"}), 503
    return jsonify({"ok": True, "status": "已连接"})


@app.route("/api/action/reset", methods=["POST"])
def api_reset():
    with state_lock:
        global last_price
        account.__init__()
        strategy.__init__(account)
        last_price = 0.0
    return jsonify({"ok": True})


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "not found"}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "server error"}), 500


def main():
    """启动Web服务器"""
    # 启动后台轮询
    poller = threading.Thread(target=background_poller, daemon=True)
    poller.start()

    print()
    print("=" * 50)
    print("  智能模拟交易系统 - Web版")
    print("=" * 50)
    print(f"  标的: {cfg.stock_name} ({cfg.stock_code})")
    print(f"  现金: {cfg.initial_cash:,.2f} HKD")
    print(f"  地址: http://localhost:5000")
    print(f"  策略: 前{cfg.avg_minutes}分钟均价 +/- {abs(cfg.stop_loss_ratio)*100:.1f}%")
    print("=" * 50)
    print("  Ctrl+C 退出")
    print()

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
        use_reloader=False,
    )


if __name__ == "__main__":
    main()
