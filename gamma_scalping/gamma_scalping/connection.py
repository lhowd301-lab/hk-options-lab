"""FutuOpenD connection manager"""
import logging
import time
from typing import Optional
from futu import OpenQuoteContext, OpenSecTradeContext, SubType, RET_OK
from .config import Config

logger = logging.getLogger("GammaScalping.Connection")


class FutuConnection:
   """Manages FutuOpenD connections
   
   - Quote context: created on connect(), polling-based price
   - Trade context: lazy-initialized on first use
   """
   
   def __init__(self, config: Config):
       self._cfg = config
       self._quote_ctx: Optional[OpenQuoteContext] = None
       self._trade_ctx: Optional[OpenSecTradeContext] = None
       self._acc_id: Optional[int] = None
       self._connected = False
       self._stock_subscribed = False
   
   def connect(self) -> bool:
       """Connect QuoteContext only (fast)"""
       try:
           logger.info("Connecting QuoteContext...")
           self._quote_ctx = OpenQuoteContext(
               host=self._cfg.futu_host,
               port=self._cfg.futu_quote_port,
           )
           logger.info("QuoteContext connected")
           self._connected = True
           return True
       except Exception as e:
           logger.error(f"QuoteContext connection failed: {e}")
           return False
   
   def ensure_trade_context(self) -> bool:
       """Lazy-init trade context. Returns True if ready."""
       if self._trade_ctx is not None and self._acc_id is not None:
           return True
       try:
           logger.info("Initializing TradeContext...")
           self._trade_ctx = OpenSecTradeContext(
               filter_trdmarket=self._cfg.futu_trd_market,
               host=self._cfg.futu_host,
               port=self._cfg.futu_trade_port,
           )
           ret, accounts = self._trade_ctx.get_account_list()
           if ret != RET_OK:
               logger.error(f"Get account list failed: {accounts}")
               return False
           if accounts is None or len(accounts) == 0:
               logger.error("No trading accounts available")
               return False
           
           env = self._cfg.futu_trade_env
           for i in range(len(accounts)):
               row = accounts.iloc[i]
               acc_env = str(row.get("trd_env", ""))
               if env.upper() in acc_env.upper():
                   self._acc_id = int(row.get("acc_id", 0))
                   break
           if self._acc_id is None:
               self._acc_id = int(accounts.iloc[0].get("acc_id", 0))
               logger.warning(f"Using first account: {self._acc_id}")
           
           if self._cfg.futu_password:
               ret, _ = self._trade_ctx.unlock_trade(password=self._cfg.futu_password)
               if ret != RET_OK:
                   logger.warning("Trade unlock failed, continuing anyway")
           
           logger.info(f"TradeContext ready, account={self._acc_id}")
           return True
       except Exception as e:
           logger.error(f"TradeContext init failed: {e}")
           return False
   
   def subscribe_stock(self, code: str) -> bool:
       """Subscribe to stock quotes (polling mode)"""
       if self._stock_subscribed:
           return True
       try:
           ret, data = self._quote_ctx.subscribe([code], [SubType.QUOTE, SubType.K_DAY])
           if ret != RET_OK:
               logger.warning(f"Subscribe failed: {data}")
               return False
           self._stock_subscribed = True
           logger.info(f"Subscribed: {code}")
           return True
       except Exception as e:
           logger.error(f"Subscribe error: {e}")
           return False
   
   def subscribe_option(self, code: str) -> bool:
       """Subscribe to option contract quotes"""
       try:
           ret, data = self._quote_ctx.subscribe([code], [SubType.QUOTE, SubType.K_DAY])
           if ret != RET_OK:
               logger.warning(f"Option subscribe failed: {data}")
               return False
           logger.info(f"Subscribed option: {code}")
           return True
       except Exception as e:
           logger.error(f"Option subscribe error: {e}")
           return False
   
   def get_stock_price(self) -> float:
       """Poll current stock price from subscribed data"""
       try:
           ret, data = self._quote_ctx.get_stock_quote([self._cfg.underlying_code])
           if ret == RET_OK and data is not None and len(data) > 0:
               return float(data.iloc[0].get("last_price", 0) or 0)
       except Exception:
           pass
       return 0.0
   
   def get_stock_day_change_pct(self) -> float:
       """Get today's stock change percentage"""
       try:
           ret, data = self._quote_ctx.get_stock_quote([self._cfg.underlying_code])
           if ret == RET_OK and data is not None and len(data) > 0:
               return float(data.iloc[0].get("change_rate", 0) or 0)
       except Exception:
           pass
       return 0.0
   
   def disconnect(self):
       """Close all connections"""
       try:
           if self._quote_ctx:
               self._quote_ctx.close()
           if self._trade_ctx:
               self._trade_ctx.close()
       except Exception as e:
           logger.error(f"Disconnect error: {e}")
       self._connected = False
       self._stock_subscribed = False
       logger.info("Connections closed")
   
   @property
   def quote_ctx(self) -> Optional[OpenQuoteContext]:
       return self._quote_ctx
   
   @property
   def trade_ctx(self) -> Optional[OpenSecTradeContext]:
       return self._trade_ctx
   
   @property
   def acc_id(self) -> Optional[int]:
       return self._acc_id
   
   @property
   def is_connected(self) -> bool:
       return self._connected
