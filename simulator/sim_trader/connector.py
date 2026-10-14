"""
智能模拟交易系统 - Futu API连接器

通过富途 OpenAPI 获取实时行情和K线数据
"""
import logging
import threading
from typing import Optional, Callable, List
from datetime import datetime

from futu import (
    OpenQuoteContext, StockQuoteHandlerBase,
    SubType, RET_OK, RET_ERROR, KLType, SecurityStatus
)

from .config import CONFIG

logger = logging.getLogger("connector")


class QuotePushHandler(StockQuoteHandlerBase):
    """实时行情推送处理器"""

    def __init__(self, on_quote: Callable[[str, float], None]):
        super().__init__()
        self._on_quote = on_quote

    def on_recv_rsp(self, rsp_pb):
        ret_code, content = super().on_recv_rsp(rsp_pb)
        if ret_code != RET_OK:
            logger.warning("行情推送异常: %s", content)
            return RET_ERROR, content

        # content 是 BasicQot namedtuple 列表
        for qot in content:
            code = qot.code
            price = qot.last_price
            # 跳过空价格
            if price > 0 and self._on_quote:
                self._on_quote(code, price)
        return RET_OK, content


class FutuConnector:
    """Futu API 连接管理器"""

    def __init__(self):
        self._quote_ctx: Optional[OpenQuoteContext] = None
        self._handler: Optional[QuotePushHandler] = None
        self._connected = False
        self._subscription_active = False
        self._lock = threading.Lock()
        # 最新行情缓存
        self.last_price: float = 0.0
        self.last_time: str = ""

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        """连接到富途 OpenAPI"""
        logger.info(
            "正在连接富途 OpenAPI: %s:%d",
            CONFIG.futu_host, CONFIG.futu_quote_port,
        )
        try:
            self._quote_ctx = OpenQuoteContext(
                host=CONFIG.futu_host,
                port=CONFIG.futu_quote_port,
            )
            self._connected = True
            logger.info("富途 OpenAPI 连接成功")
            return True
        except Exception as e:
            logger.error("富途 OpenAPI 连接失败: %s", e)
            self._connected = False
            return False

    def subscribe(self, on_quote: Callable[[str, float], None]) -> bool:
        """订阅实时行情"""
        if not self._connected or not self._quote_ctx:
            logger.error("尚未连接, 无法订阅")
            return False

        ctx = self._quote_ctx

        # 注册推送处理器
        self._handler = QuotePushHandler(on_quote)
        ctx.set_handler(self._handler)

        # 订阅 QUOTE (实时报价)
        ret, msg = ctx.subscribe(
            [CONFIG.stock_code],
            [SubType.QUOTE],
        )
        if ret != RET_OK:
            logger.error("订阅行情失败: %s", msg)
            return False

        # 也订阅 1分钟 K 线用于基准计算
        ret2, msg2 = ctx.subscribe(
            [CONFIG.stock_code],
            [SubType.K_1M],
        )
        if ret2 != RET_OK:
            logger.warning("订阅1分钟K线失败: %s", msg2)

        self._subscription_active = True
        logger.info("行情订阅成功: %s", CONFIG.stock_code)
        return True

    def get_current_quote(self) -> Optional[float]:
        """主动获取当前最新价格"""
        if not self._connected or not self._quote_ctx:
            return None
        try:
            ret, data = self._quote_ctx.get_stock_quote([CONFIG.stock_code])
            if ret != RET_OK or data.empty:
                return None
            row = data.iloc[0]
            self.last_price = float(row["last_price"])
            self.last_time = f"{row['data_date']} {row['data_time']}"
            return self.last_price
        except Exception as e:
            logger.warning("获取价格失败: %s", e)
            return None

    def get_today_1min_klines(self) -> List[float]:
        """获取今日 1分钟 K线收盘价"""
        if not self._connected or not self._quote_ctx:
            return []
        try:
            ktype = KLType.K_1M
            ret, data = self._quote_ctx.get_cur_kline(
                CONFIG.stock_code,
                50,            # 取最近50个1分钟K线
                ktype,
            )
            if ret != RET_OK or data is None or data.empty:
                return []
            # 取收盘价
            prices = data["close"].tolist()
            return [float(p) for p in prices if p > 0]
        except Exception as e:
            logger.warning("获取K线数据失败: %s", e)
            return []

    def get_market_state(self) -> str:
        """获取市场状态"""
        if not self._connected or not self._quote_ctx:
            return "未知"
        try:
            ret, data = self._quote_ctx.get_market_state([CONFIG.stock_code])
            if ret != RET_OK or data.empty:
                return "未知"
            return str(data.iloc[0]["market_state"])
        except Exception:
            return "未知"

    def disconnect(self):
        """断开连接"""
        with self._lock:
            if self._quote_ctx:
                try:
                    self._quote_ctx.unsubscribe_all()
                    self._quote_ctx.close()
                except Exception:
                    pass
                self._quote_ctx = None
            self._connected = False
            self._subscription_active = False
        logger.info("富途 API 已断开")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()
