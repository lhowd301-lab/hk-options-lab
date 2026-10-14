"""
智能模拟交易系统 - 实时盯盘面板 (终端UI)
"""
import os
import logging
from typing import Optional
from datetime import datetime
from .config import CONFIG
from .simulation_account import SimulationAccount
from .strategy import TradingStrategy

logger = logging.getLogger("dashboard")

_T = "TOP"
_M = "MID"
_B = "BOT"
_S = "SEP"


class Dashboard:
    """终端实时盯盘面板"""

    def __init__(self, account: SimulationAccount, strategy: TradingStrategy):
        self.account = account
        self.strategy = strategy
        self.current_price: float = 0.0
        self.price_change: float = 0.0
        self.price_change_pct: float = 0.0
        self.prev_close: float = 0.0
        self.conn_status: str = "未连接"
        self.market_status: str = "未知"
        self.last_update_time: str = "--:--:--"
        self._error_msg: Optional[str] = None

    def clear(self):
        """清屏"""
        os.system("cls" if os.name == "nt" else "clear")

    def _box_line(self, left: str, fill: str, mid: str, right: str, width: int) -> str:
        return left + mid * (width - 2) + right

    def _line(self, text: str, width: int = 64) -> str:
        return " " + text.ljust(width - 4) + " "

    def _section(self, rows: list, width: int = 64) -> str:
        lines = []
        for r in rows:
            if r == _T:
                lines.append(self._box_line("\u2554", "\u2550", "\u2550", "\u2557", width))
            elif r == _B:
                lines.append(self._box_line("\u255a", "\u2550", "\u2550", "\u255d", width))
            elif r == _M:
                lines.append(self._box_line("\u255f", "\u2500", "\u2500", "\u2562", width))
            elif r == _S:
                lines.append(self._box_line("\u2551", " ", " ", "\u2551", width) + "    ")
            else:
                lines.append("\u2551" + self._line(str(r), width) + "\u2551")
        return "\n".join(lines)

    def update_price(self, price: float, prev_close: float = 0.0):
        self.current_price = price
        if prev_close > 0:
            self.prev_close = prev_close
        if self.prev_close > 0:
            self.price_change = price - self.prev_close
            self.price_change_pct = self.price_change / self.prev_close * 100
        self.last_update_time = datetime.now().strftime("%H:%M:%S")

    def set_error(self, msg: str):
        self._error_msg = msg

    def render(self) -> str:
        """渲染完整面板"""
        acct = self.account
        s = self.strategy
        w = 64

        price_str = f"{self.current_price:.4f}" if self.current_price > 0 else "--"
        pct_sign = "+" if self.price_change_pct >= 0 else ""
        pct_str = f"{pct_sign}{self.price_change:.4f} ({pct_sign}{self.price_change_pct:.2f}%)" if self.prev_close > 0 else "--"

        # 均价
        avg = acct.avg_price_30min
        avg_str = f"{avg:.4f}" if avg else "收集中..."
        stop_loss = s.stop_loss_price
        stop_str = f"{stop_loss:.4f}" if stop_loss else "N/A"

        # 价差
        if self.current_price > 0 and avg and avg > 0:
            diff = self.current_price - avg
            diff_pct = diff / avg * 100
            diff_str = f"{diff:+.4f} ({diff_pct:+.2f}%)"
        else:
            diff_str = "--"

        # 账户
        mkt_val = acct.market_value(self.current_price) if self.current_price > 0 else 0
        total = acct.total_assets(self.current_price) if self.current_price > 0 else acct.cash
        pnl_val = acct.pnl(self.current_price) if self.current_price > 0 else 0
        pnl_pct_val = acct.pnl_pct(self.current_price) if self.current_price > 0 else 0

        # 最新交易
        last_trade = ""
        if acct.trade_log:
            t = acct.trade_log[-1]
            last_trade = f"{t.time} {t.action} {t.shares}股 @ {t.price:.4f} (金额{t.amount:.2f})"
        else:
            last_trade = "暂无交易"

        # 连接状态
        avg_time = f"锁定于 {acct.avg_set_time}" if acct.avg_set_time else ""

        sections = []

        # === 标题 ===
        sections.append(self._section([
            _T,
            f"     \u667a\u80fd\u6a21\u62df\u4ea4\u6613\u7cfb\u7edf  v1.0",
            f"     {CONFIG.stock_name} ({CONFIG.stock_code})  \u6052\u751f\u79d1\u6280",
            _S,
        ], w))

        # === 行情 ===
        sections.append(self._section([
            _M,
            f"  \u5f53\u524d\u4ef7: \u00a0{price_str}\u00a0\u00a0\u00a0\u6da8\u8dcc\u5e45: {pct_str}",
            f"  \u5747\u4ef7:  \u00a0{avg_str}\u00a0\u00a0\u00a0\u6b62\u635f\u7ebf: {stop_str}",
            f"  \u4ef7\u5dee:  {diff_str}",
            f"  \u57fa\u51c6\u65f6\u6bb5: {CONFIG.market_open.strftime('%H:%M')}-{CONFIG.avg_end_time.strftime('%H:%M')}",
        ], w))

        # === 账户 ===
        sections.append(self._section([
            _M,
            f"  \u73b0\u91d1:   \u00a0{acct.cash:>14,.2f}",
            f"  \u6301\u4ed3:   \u00a0{acct.position:>10} \u80a1  |  \u6210\u672c {acct.avg_cost:.4f}" if acct.position > 0 else f"  \u6301\u4ed3:   \u00a0{acct.position:>10} \u80a1  |  \u7a7a\u4ed3",
            f"  \u5e02\u503c:   \u00a0{mkt_val:>14,.2f}",
            f"  \u603b\u8d44\u4ea7: {total:>14,.2f}",
            f"  \u76c8\u4e8f:   {pnl_val:>+14,.2f} ({pnl_pct_val:>+8.2f}%)",
        ], w))

        # === 策略 ===
        signal = s.get_signal_text()
        signal_trunc = signal[:58] if len(signal) > 58 else signal
        sections.append(self._section([
            _M,
            f"  \u4fe1\u53f7: {signal_trunc}",
            f"  \u6700\u65b0\u4ea4\u6613: {last_trade[:56] if len(last_trade) > 56 else last_trade}",
        ], w))

        # === 状态栏 ===
        status = f"  [\u5bcc\u9014API: {self.conn_status}]  [{self.market_status}]  \u66f4\u65b0: {self.last_update_time}"
        if self._error_msg:
            status += f"  \u9519\u8bef: {self._error_msg}"

        sections.append(self._section([
            _M,
            status,
            _B,
        ], w))

        return "\n".join(sections)

    def show(self):
        """显示面板"""
        self.clear()
        print(self.render())
        print()

    def show_no_api(self):
        """显示无API连接时的脱机面板"""
        acct = self.account
        w = 64

        text = f"""
\u250f{"="*62}\u2513
\u2503  \u667a\u80fd\u6a21\u62df\u4ea4\u6613\u7cfb\u7edf  v1.0                        \u2503
\u2503  {CONFIG.stock_name} ({CONFIG.stock_code})  \u6052\u751f\u79d1\u6280                   \u2503
\u2503{" "*62}\u2503
\u2503  \u5f53\u524d\u72b6\u6001: \u8fd0\u884c\u5728\u8131\u673a\u6a21\u5f0f (\u6d4b\u8bd5/\u6a21\u62df)               \u2503
\u2503  \u521d\u59cb\u73b0\u91d1: HKD {acct.initial_cash:>,.2f}                                \u2503
\u2503{" "*62}\u2503
\u2503  \u7b56\u7565\u53c2\u6570:                                                  \u2503
\u2503    \u57fa\u51c6\u65f6\u6bb5: {CONFIG.market_open.strftime("%H:%M")}-{CONFIG.avg_end_time.strftime("%H:%M")} ({CONFIG.avg_minutes}\u5206\u949f\u5747\u4ef7)                     \u2503
\u2503    \u4e70\u5165\u89e6\u53d1: \u5f53\u524d\u4ef7 > \u5747\u4ef7 -> \u4e70\u5165\u6301\u4ed3\u5e02\u503c {CONFIG.buy_ratio*100:.0f}%                    \u2503
\u2503    \u6b62\u635f\u89e6\u53d1: \u5f53\u524d\u4ef7 < \u5747\u4ef7 x {1+CONFIG.stop_loss_ratio:.1f} -> \u5168\u90e8\u6e05\u4ed3              \u2503
\u2503{" "*62}\u2503
\u2503  \u2727 \u8bf7\u786e\u4fdd\u5bcc\u9014 OpenAPI \u5df2\u542f\u52a8\u5e76\u8fde\u63a5                     \u2503
\u2503  \u2727 \u9ed8\u8ba4\u8fde\u63a5\u5730\u5740: {CONFIG.futu_host}:{CONFIG.futu_quote_port}                               \u2503
\u2503{" "*62}\u2503
\u2503  \u6309 Enter \u91cd\u8bd5\u8fde\u63a5, Ctrl+C \u9000\u51fa                              \u2503
\u251a{"="*62}\u251d
"""
        self.clear()
        print(text)
