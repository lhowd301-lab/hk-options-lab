"""Bot controller for web interface - runs GammaScalpingBot in background thread"""

from __future__ import annotations

import asyncio
import datetime
import logging
import threading
import time
from typing import Any, Dict, List, Optional


class BotController:
    """Controls the Gamma Scalping bot from the web interface"""
    
    def __init__(self, config_path: str = "config.yaml"):
        self._config_path = config_path
        self._bot: Optional[Any] = None
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._running = False
        self._lock = threading.Lock()
        self._start_price_poller()
        
        # Shared state (thread-safe)
        self._state: Dict[str, Any] = {
            "status": "stopped",
            "price": 0.0,
            "day_change_pct": 0.0,
            "atr": 0.0,
            "option_code": "",
            "option_delta": 0.0,
            "option_gamma": 0.0,
            "option_theta": 0.0,
            "option_vega": 0.0,
            "implied_volatility": 0.0,
            "option_price": 0.0,
            "strike_price": 0.0,
            "stock_shares": 0,
            "net_delta": 0.0,
            "unrealized_pnl": 0.0,
            "realized_pnl": 0.0,
            "trade_count": 0,
            "signal_count": 0,
            "greeks_source": "",
            "error": "",
        }
        self._logs: List[str] = []
        self._max_logs = 200
    
    def start(self) -> bool:
        """Start the bot in a background thread"""
        if self._running:
            return True
        
        self._running = True
        self._thread = threading.Thread(target=self._run_bot, daemon=True)
        self._thread.start()
        self._add_log("INFO", "Bot started")
        return True
    
    def stop(self):
        """Stop the bot"""
        self._running = False
        if self._bot:
            self._bot._running = False
        self._add_log("INFO", "Bot stopped")
        self._update_state(status="stopped")
    

    def _start_price_poller(self):
        self._poller_running = True
        self._poller_thread = threading.Thread(target=self._price_poll_loop, daemon=True)
        self._poller_thread.start()
    
    def _price_poll_loop(self):
        import time
        try:
            from futu import OpenQuoteContext, SubType, RET_OK
            from .config import Config
            c = Config.load(self._config_path)
            ctx = OpenQuoteContext(host=c.futu_host, port=c.futu_quote_port)
            ctx.subscribe([c.underlying_code], [SubType.QUOTE])
            self._add_log("INFO", "Price poller started")
            while self._poller_running:
                try:
                    ret, data = ctx.get_stock_quote([c.underlying_code])
                    if ret == RET_OK and data is not None and len(data) > 0:
                        r = data.iloc[0]
                        p = float(r.get("last_price", 0) or 0)
                        chg = float(r.get("change_rate", 0) or 0)
                        if p > 0:
                            self._update_state(price=p, day_change_pct=chg)
                    time.sleep(0.5)
                except:
                    time.sleep(1.0)
        except Exception as e:
            self._add_log("WARNING", "Price poller error: " + str(e))
        finally:
            self._add_log("INFO", "Price poller stopped")

    def _run_bot(self):
        """Run the bot in a background thread"""
        try:
            from .main import GammaScalpingBot
            
            self._bot = GammaScalpingBot(self._config_path)
            
            # Redirect logger to capture logs
            self._setup_log_capture()
            
            if not self._bot.initialize():
                self._add_log("ERROR", "Bot initialization failed")
                self._update_state(status="error", error="Initialization failed")
                self._running = False
                return
            
            self._update_state(status="running")
            self._add_log("INFO", "Bot initialized successfully")
            
            # Run the main loop (modified to update shared state)
            self._run_main_loop()
            
        except Exception as e:
            self._add_log("ERROR", f"Bot error: {e}")
            self._update_state(status="error", error=str(e))
        finally:
            self._running = False
            self._update_state(status="stopped")
    
    def _run_main_loop(self):
        """Run the adapted main loop that updates shared state"""
        bot = self._bot
        
        # Wait for market open
        if not asyncio.run(bot._wait_market_open()):
            self._add_log("WARNING", "Market not open, running anyway")
        
        # Select option contract
        self._add_log("INFO", "Selecting option contract...")
        contract = bot._select_option_contract()
        if contract is None:
            self._add_log("ERROR", "No suitable option contract")
            return
        
        # Subscribe option
        bot._connection.subscribe_option(contract.code)
        
        # Get initial Greeks from cached data
        bot._poll_price(retries=3)
        from .models import GreeksSnapshot, OptionSide
        import datetime as dt
        greeks = GreeksSnapshot(
            timestamp=dt.datetime.now(),
            option_code=contract.code,
            underlying_price=bot._current_price,
            option_price=contract.last_price,
            delta=contract.delta,
            gamma=contract.gamma,
            theta=contract.theta,
            vega=contract.vega,
            rho=0.0,
            implied_volatility=contract.implied_volatility,
            strike_price=contract.strike_price,
            days_to_expiry=contract.days_to_expiry,
            option_type=contract.option_type,
        )
        
        # Open position
        bot._position_opened = False
        bot._open_position(contract.code, greeks)
        
        # Update state with initial data
        self._update_from_portfolio(greeks)
        
        self._add_log("INFO", "Entering main loop")
        
        # Main loop
        last_log_time = 0.0
        last_greeks_refresh = 0.0
        
        while self._running and bot._running:
            try:
                now = time.time()
                
                # Poll stock price
                bot._current_price = bot._connection.get_stock_price()
                if bot._current_price <= 0:
                    time.sleep(0.2)
                    continue
                
                bot._greeks_engine.update_underlying_price(bot._current_price)
                day_change = bot._connection.get_stock_day_change_pct()
                
                # Always update price in shared state
                self._update_state(price=bot._current_price, day_change_pct=day_change)
                
                # Refresh Greeks every 2 seconds (keep old on failure)
                if now - last_greeks_refresh >= 2.0:
                    new_g = self._refresh_greeks(contract.code, bot._current_price)
                    if new_g is not None:
                        greeks = new_g
                        last_greeks_refresh = now
                
                if greeks:
                    state = bot._portfolio.get_state(greeks)
                    self._update_from_portfolio(greeks, state, day_change)
                    
                    # Check signals
                    signal = bot._signal_engine.evaluate(
                        state, bot._current_atr, day_change
                    )
                    if signal:
                        self._add_log("SIGNAL", f"{signal.signal_type.name}: {signal.reason}")
                
                # Check close time
                hk_now = dt.datetime.now()
                if bot._risk.check_close_time(hk_now) and bot._portfolio.is_open and not bot._risk.close_executed:
                    bot._execute_close_all()
                    bot._risk.mark_close_executed()
                    self._add_log("WARNING", "Market close - positions closed")
                
                time.sleep(0.5)
                
            except Exception as e:
                self._add_log("ERROR", f"Loop error: {e}")
                time.sleep(1.0)
        
        # Cleanup
        if bot._portfolio.is_open:
            bot._execute_close_all()
        bot._connection.disconnect()
        self._add_log("INFO", "Bot stopped cleanly")
    
    def _refresh_greeks(self, option_code: str, price: float) -> Optional[Any]:
        """Refresh Greeks using a fresh connection (avoids stale context)"""
        try:
            from .config import Config
            from .greeks import GreeksEngine
            from futu import OpenQuoteContext
            
            cfg = Config.load(self._config_path)
            fc = OpenQuoteContext(host=cfg.futu_host, port=cfg.futu_quote_port)
            eng = GreeksEngine(fc, cfg)
            eng.update_underlying_price(price)
            greeks = eng.fetch_greeks(option_code, price)
            fc.close()
            return greeks
        except Exception as e:
            self._add_log("DEBUG", f"Greeks refresh failed: {e}")
            return None
    
    def _update_from_portfolio(self, greeks: Optional[Any] = None, state: Optional[Any] = None, day_change: float = 0.0):
        """Update shared state from portfolio data"""
        with self._lock:
            s = self._state
            s["day_change_pct"] = day_change
            
            if greeks:
                s["price"] = greeks.underlying_price
                s["option_code"] = greeks.option_code
                s["option_delta"] = round(greeks.delta, 4)
                s["option_gamma"] = round(greeks.gamma, 4)
                s["option_theta"] = round(greeks.theta, 4)
                s["option_vega"] = round(greeks.vega, 4)
                s["implied_volatility"] = round(greeks.implied_volatility, 2)
                s["option_price"] = round(greeks.option_price, 2)
                s["strike_price"] = greeks.strike_price
                s["greeks_source"] = self._bot._greeks_engine.last_source if self._bot else ""
            
            if state:
                s["net_delta"] = round(state.net_delta, 4)
                s["stock_shares"] = state.stock_shares
                s["unrealized_pnl"] = round(state.unrealized_pnl, 2)
                s["realized_pnl"] = round(state.realized_pnl, 2)
            
            if self._bot:
                s["trade_count"] = self._bot._portfolio.trade_count if self._bot._portfolio else 0
                s["signal_count"] = self._bot._signal_engine.signal_count if self._bot._signal_engine else 0
                s["atr"] = round(self._bot._current_atr, 4)
    
    def get_state(self) -> Dict[str, Any]:
        """Get current state (thread-safe)"""
        with self._lock:
            return dict(self._state)
    
    def get_logs(self, since: Optional[float] = None) -> List[Dict[str, Any]]:
        """Get logs since timestamp"""
        if since is None:
            return list(self._logs[-50:])
        return [log for log in self._logs if log["time"] > since]
    
    def close_all(self):
        """Close all positions"""
        if self._bot and self._bot._portfolio.is_open:
            self._bot._execute_close_all()
            self._add_log("WARNING", "All positions closed via web")
    
    def _update_state(self, **kwargs):
        with self._lock:
            for k, v in kwargs.items():
                self._state[k] = v
    
    def _add_log(self, level: str, message: str):
        entry = {
            "time": time.time(),
            "level": level,
            "message": message,
        }
        self._logs.append(entry)
        if len(self._logs) > self._max_logs:
            self._logs = self._logs[-self._max_logs:]
    
    def _setup_log_capture(self):
        """Redirect Python logging to our log buffer"""
        class LogHandler(logging.Handler):
            def __init__(self, controller):
                super().__init__()
                self._controller = controller
            def emit(self, record):
                self._controller._add_log(record.levelname, record.getMessage())
        
        handler = LogHandler(self)
        handler.setLevel(logging.INFO)
        logging.getLogger("GammaScalping").addHandler(handler)
    
    @property
    def is_running(self) -> bool:
        return self._running


# Helper: run async function synchronously
