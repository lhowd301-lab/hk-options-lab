"""ATR (Average True Range) calculation"""
import logging

logger = logging.getLogger("GammaScalping.ATR")


def calculate_atr(highs, lows, closes, period=14, prev_atr=None):
    """Calculate ATR"""
    if len(highs) < 2:
        return 0.0
    tr_list = []
    for i in range(1, len(highs)):
        h, l, pc = highs[i], lows[i], closes[i - 1]
        tr_list.append(max(h - l, abs(h - pc), abs(l - pc)))
    if not tr_list:
        return 0.0
    if prev_atr is not None and len(tr_list) >= 1:
        atr = (prev_atr * (period - 1) + tr_list[-1]) / period
    else:
        atr = sum(tr_list[:period]) / min(len(tr_list), period)
    return atr


def fetch_atr_from_kline(quote_ctx, code, period=14):
    """Fetch K-line data and calculate ATR"""
    from futu import KLType, RET_OK
    ret, data = quote_ctx.get_cur_kline(code, ktype=KLType.K_DAY, num=period + 6)
    if ret != RET_OK:
        logger.error("Failed to get K-line: " + str(data))
        return 0.0
    if data is None or len(data) == 0:
        logger.warning("Empty K-line data")
        return 0.0
    highs = data["high"].tolist()
    lows = data["low"].tolist()
    closes = data["close"].tolist()
    atr = calculate_atr(highs, lows, closes, period)
    logger.info("ATR(" + str(period) + ") = " + str(round(atr, 4)))
    return atr
