"""
智能模拟交易系统 - 主入口

用法:
  python -m sim_trader.main                    # 默认50万现金
  python -m sim_trader.main --cash 100000      # 指定10万现金
  python -m sim_trader.main --code HK.00981    # 指定股票代码
"""
import sys
import time
import argparse
import logging

# Windows console UTF-8 support
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from datetime import datetime

from .config import CONFIG
from .simulation_account import SimulationAccount
from .strategy import TradingStrategy
from .connector import FutuConnector
from .dashboard import Dashboard

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


def parse_args():
    parser = argparse.ArgumentParser(description="智能模拟交易系统")
    parser.add_argument("--cash", type=float, default=None,
                        help="初始现金 (HKD), 默认 %.0f" % CONFIG.initial_cash)
    parser.add_argument("--code", type=str, default=None,
                        help="股票代码, 默认 %s" % CONFIG.stock_code)
    parser.add_argument("--futu-host", type=str, default=None,
                        help="富途API主机, 默认 %s" % CONFIG.futu_host)
    parser.add_argument("--futu-port", type=int, default=None,
                        help="富途API行情端口, 默认 %d" % CONFIG.futu_quote_port)
    return parser.parse_args()


def apply_args(args):
    if args.cash is not None:
        CONFIG.initial_cash = args.cash
    if args.code is not None:
        CONFIG.stock_code = args.code
    if args.futu_host is not None:
        CONFIG.futu_host = args.futu_host
    if args.futu_port is not None:
        CONFIG.futu_quote_port = args.futu_port
    logger.info("配置: 现金=%.2f  股票=%s", CONFIG.initial_cash, CONFIG.stock_code)


def run():
    """主运行函数"""
    args = parse_args()
    apply_args(args)

    # 初始化组件
    account = SimulationAccount()
    strategy = TradingStrategy(account)
    connector = FutuConnector()
    dashboard = Dashboard(account, strategy)

    # 股价更新回调 (从推送线程调用)
    def on_price_update(code: str, price: float):
        dashboard.conn_status = "已连接"
        dashboard.update_price(price)

        # 喂给策略
        trade_signal = strategy.feed_price(price)
        if trade_signal:
            logger.info("[信号] %s", trade_signal)

    # === 尝试连接 Futu API ===
    connected = connector.connect()
    if connected:
        # 获取初始数据
        quote = connector.get_current_quote()
        if quote:
            dashboard.update_price(quote)

        # 获取今日 K 线补充基准数据
        kline_prices = connector.get_today_1min_klines()
        for p in kline_prices:
            strategy.feed_price(p)

        # 订阅实时推送
        sub_ok = connector.subscribe(on_price_update)
        if sub_ok:
            dashboard.conn_status = "已连接"
            dashboard.market_status = connector.get_market_state()
        else:
            dashboard.conn_status = "订阅失败"

    if not connected:
        dashboard.conn_status = "未连接"

    # === 主循环 ===
    logger.info("智能模拟交易系统启动完成")
    try:
        last_quote_poll = 0

        while True:
            # 如果连接了但有数据缓存, 定期轮询作为补充
            if connected:
                now = time.time()
                if now - last_quote_poll > 5:  # 每5秒主动轮询
                    quote = connector.get_current_quote()
                    if quote and quote != dashboard.current_price:
                        dashboard.update_price(quote)
                        trade_signal = strategy.feed_price(quote)
                        if trade_signal:
                            logger.info("[信号] %s", trade_signal)
                    last_quote_poll = now

            # 刷新面板
            try:
                dashboard.show()
            except Exception:
                pass  # skip render errors

            # 等待
            time.sleep(CONFIG.refresh_interval)

    except KeyboardInterrupt:
        logger.info("用户中断, 正在退出...")
    finally:
        connector.disconnect()
        # 最终面板
        try:
            dashboard.show()
        except Exception:
            pass  # skip render errors

    # === 结束摘要 ===
    print()
    print("=" * 60)
    print("  交易会话结束")
    print("=" * 60)
    print(f"  股票:    {CONFIG.stock_name} ({CONFIG.stock_code})")
    print(f"  初始现金: HKD {account.initial_cash:,.2f}")
    print(f"  最终现金: HKD {account.cash:,.2f}")
    print(f"  最终持仓: {account.position} 股")
    print(f"  总资产:   HKD {account.total_assets(dashboard.current_price or 1):,.2f}")
    print(f"  总盈亏:   HKD {account.pnl(dashboard.current_price or 1):+,.2f}")
    print(f"  收益率:   {account.pnl_pct(dashboard.current_price or 1):+.2f}%")
    print(f"  交易次数: {len(account.trade_log)} 笔")
    print("=" * 60)

    if account.trade_log:
        print()
        print("  交易记录:")
        for i, t in enumerate(account.trade_log, 1):
            print(f"    {i:>3}. {t.time}  {t.action:<4} {t.shares:>6}股 @ {t.price:.4f}  "
                  f"金额{t.amount:>10,.2f}  现金{t.cash_after:>12,.2f}")


if __name__ == "__main__":
    run()
