"""Main loop - Gamma Scalping entry point"""

from __future__ import annotations

import asyncio
import datetime
import logging
import signal
import time
from typing import Optional

from futu import (
    OpenQuoteContext, KLType, RET_OK,
)

from .config import Config
from .log import setup_logger
from .models import OptionSide, SignalType
from .connection import FutuConnection
from .option_selector import OptionSelector
from .greeks import GreeksEngine
from .portfolio import PortfolioManager
from .signal import SignalEngine
from .execution import ExecutionEngine
from .risk import RiskManager
from .atr import fetch_atr_from_kline, calculate_atr


class GammaScalpingBot:
    """Gamma Scalping main controller"""
    
    def __init__(self, config_path: str = "config.yaml"):
        self._cfg = Config.load(config_path)
        self._logger = setup_logger("GammaScalping", self._cfg)
        
        self._connection: Optional[FutuConnection] = None
        self._option_selector: Optional[OptionSelector] = None
        self._greeks_engine: Optional[GreeksEngine] = None
        self._portfolio: Optional[PortfolioManager] = None
        self._signal_engine: Optional[SignalEngine] = None
        self._execution: Optional[ExecutionEngine] = None
        self._risk: Optional[RiskManager] = None
        
        self._running = False
        self._current_price: float = 0.0
        self._current_atr: float = 0.0
        self._position_opened: bool = False
        self._trade_init_attempted: bool = False
        
        self._greeks_log: list = []
    
    def initialize(self) -> bool:
        """Initialize subsystems"""
        self._logger.info("=" * 60)
        self._logger.info("Gamma Scalping System starting")
        self._logger.info(f"Underlying: {self._cfg.underlying_code}")
        self._logger.info("=" * 60)
        
        # 1. Connect QuoteContext
        self._connection = FutuConnection(self._cfg)
        if not self._connection.connect():
            self._logger.error("FutuOpenD connection failed")
            return False
        
        qc = self._connection.quote_ctx
        
        # 2. Init subsystems
        self._portfolio = PortfolioManager(self._cfg)
        self._signal_engine = SignalEngine(self._cfg)
        self._risk = RiskManager(self._cfg, self._portfolio)
        self._greeks_engine = GreeksEngine(qc, self._cfg)
        self._option_selector = OptionSelector(qc, self._cfg)
        
        # 3. Subscribe stock
        self._connection.subscribe_stock(self._cfg.underlying_code)
        
        # 4. Get initial price
        self._poll_price(retries=5)
        if self._current_price <= 0:
            self._logger.warning("Could not get initial stock price")
        
        # 5. Fetch ATR
        self._current_atr = fetch_atr_from_kline(
            qc, self._cfg.underlying_code, self._cfg.atr_period
        )
        
        self._logger.info(f"Initial price: {self._current_price:.2f}, ATR: {self._current_atr:.4f}")
        return True
    
    def _poll_price(self, retries: int = 3, delay: float = 0.5) -> float:
        """Poll stock price with retries"""
        for i in range(retries):
            price = self._connection.get_stock_price()
            if price > 0:
                self._current_price = price
                return price
            if i < retries - 1:
                time.sleep(delay)
        return self._current_price
    
    async def run(self):
        """Main event loop"""
        self._running = True
        
        # Wait for market open
        if not await self._wait_market_open():
            self._logger.error("Not market hours, exiting")
            return
        
        # Select option contract
        self._logger.info("Selecting option contract...")
        contract = self._select_option_contract()
        if contract is None:
            self._logger.error("No suitable option contract found")
            return
        
        # Subscribe option
        self._connection.subscribe_option(contract.code)
        
        # Use Greeks from option selector (already fetched)
        self._logger.info("Using cached Greeks from option selector...")
        self._poll_price(retries=3)
        from .models import GreeksSnapshot, OptionSide
        import datetime
        greeks = GreeksSnapshot(
            timestamp=datetime.datetime.now(),
            option_code=contract.code,
            underlying_price=self._current_price,
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
        self._logger.info("Built Greeks from contract data...")

        if greeks is None:
            self._logger.error("Could not get initial Greeks")
            return
            self._logger.error("Could not fetch initial Greeks")
            return
        
        # Initialize trade context (lazy)
        self._init_trade()
        
        # Open position
        if not self._position_opened:
            self._open_position(contract.code, greeks)
        
        # Main loop
        self._logger.info("Entering main loop (polling every 500ms)")
        last_log_time = 0.0
        
        while self._running:
            try:
                now = time.time()
                
                # Poll stock price
                self._current_price = self._connection.get_stock_price()
                if self._current_price <= 0:
                    await asyncio.sleep(0.2)
                    continue
                
                self._greeks_engine.update_underlying_price(self._current_price)
                
                # Get day change
                day_change = self._connection.get_stock_day_change_pct()
                
                # Check market hours
                hk_now = datetime.datetime.now()
                if not self._risk.check_market_hours(hk_now):
                    await asyncio.sleep(5.0)
                    continue
                
                # Check close time
                if self._risk.check_close_time(hk_now):
                    if self._portfolio.is_open and not self._risk.close_executed:
                        self._logger.warning("Market close imminent, closing all")
                        self._execute_close_all()
                        self._risk.mark_close_executed()
                    await asyncio.sleep(1.0)
                    continue
                
                # Fetch option Greeks & evaluate
                if self._portfolio.option_code:
                    greeks = self._greeks_engine.fetch_greeks(
                        self._portfolio.option_code, self._current_price
                    )
                    if greeks:
                        state = self._portfolio.get_state(greeks)
                        
                        if now - last_log_time >= 5.0:
                            self._log_greeks(greeks, state)
                            last_log_time = now
                        
                        signal = self._signal_engine.evaluate(
                            state, self._current_atr, day_change
                        )
                        if signal:
                            if self._check_scalp_profitability(greeks, signal):
                                self._ensure_trade_ready()
                                if self._execution is not None:
                                    self._execution.execute_signal(signal, state)
                        
                        if self._risk.check_daily_loss():
                            self._logger.warning("Daily loss limit hit")
                            self._execute_close_all()
                
                elapsed = time.time() - now
                sleep_time = max(0.05, 0.5 - elapsed)
                await asyncio.sleep(sleep_time)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Main loop error: {e}", exc_info=True)
                await asyncio.sleep(1.0)
        
        # Cleanup
        if self._portfolio.is_open:
            self._execute_close_all()
    
    def _init_trade(self):
        """Initialize trade context (lazy)"""
        if self._trade_init_attempted:
            return
        self._trade_init_attempted = True
        
        if self._connection.ensure_trade_context():
            self._execution = ExecutionEngine(
                self._connection.trade_ctx,
                self._portfolio,
                self._cfg,
            )
            self._execution.set_account(self._connection.acc_id)
            self._logger.info("Trade context ready")
        else:
            self._logger.warning("Trade context not available (simulate mode only)")
    
    def _ensure_trade_ready(self):
        """Ensure trade context is ready for orders"""
        if self._execution is None and not self._trade_init_attempted:
            self._init_trade()
    
    def _select_option_contract(self):
        """Select best option contract"""
        contracts = self._option_selector.fetch_option_chain()
        if not contracts:
            return None
        return self._option_selector.select_best_contract(contracts)
    
    def _open_position(self, option_code: str, greeks):
        """Open initial position"""
        if self._position_opened:
            return
        
        self._logger.info(
            f"Opening: {option_code} x 1, "
            f"Delta={greeks.delta:.4f}, @ {greeks.option_price:.4f}"
        )
        
        self._ensure_trade_ready()
        if self._execution is None:
            self._logger.warning("Trade context not ready, simulating position")
            self._portfolio.open_option(
                option_code, 1, greeks.option_price,
                OptionSide.CALL
            )
            hedge = round(greeks.delta * 1 * self._cfg.option_multiplier)
            if hedge > 0:
                self._portfolio.adjust_stock(-hedge, greeks.underlying_price)
            self._position_opened = True
            self._logger.info("Position opened (simulated)")
            return
        
        success = self._execution.open_initial_position(
            option_code=option_code,
            option_price=greeks.option_price,
            option_delta=greeks.delta,
            contracts=1,
        )
        if success:
            self._position_opened = True
    
    def _execute_close_all(self):
        """Close all positions"""
        if self._execution is not None:
            self._execution._close_all(self._current_price)
        elif self._portfolio.is_open:
            self._portfolio.close_all_stock(self._current_price)
            self._portfolio.close_option(self._current_price)
        self._logger.info("All positions closed")
    
    def _check_scalp_profitability(self, greeks, signal) -> bool:
        """Check if scalp covers trading costs"""
        if signal.signal_type in (SignalType.STOP_LOSS, SignalType.CLOSE_ALL):
            return True
        if self._cfg.min_scalp_profit <= 0:
            return True
        rebalance_shares = abs(signal.rebalance_shares)
        if rebalance_shares == 0:
            return False
        trade_amount = rebalance_shares * signal.underlying_price
        cost = self._portfolio.estimate_trade_cost(trade_amount)
        return cost <= self._cfg.min_scalp_profit * 0.3
    
    def _log_greeks(self, greeks, state):
        """Log Greeks state"""
        from .models import GreeksRecord
        rec = GreeksRecord(
            timestamp=greeks.timestamp,
            underlying_price=greeks.underlying_price,
            option_code=greeks.option_code,
            option_price=greeks.option_price,
            delta=greeks.delta,
            gamma=greeks.gamma,
            theta=greeks.theta,
            vega=greeks.vega,
            iv=greeks.implied_volatility,
            net_delta=state.net_delta,
            stock_shares=state.stock_shares,
            source=self._greeks_engine.last_source,
        )
        self._greeks_log.append(rec)
        self._logger.info(
            f"State | P={greeks.underlying_price:.2f} "
            f"D={greeks.delta:.4f} netD={state.net_delta:.4f} "
            f"G={greeks.gamma:.4f} T={greeks.theta:.4f} "
            f"IV={greeks.implied_volatility:.2%} "
            f"Stock={state.stock_shares:+d} "
            f"PnLU={state.unrealized_pnl:+.2f} PnLR={state.realized_pnl:+.2f}"
        )
    
    async def _wait_market_open(self) -> bool:
        """Wait for market to open"""
        for _ in range(600):
            if self._risk.check_market_hours():
                self._logger.info("Market is open")
                return True
            await asyncio.sleep(1.0)
        return False
    
    def shutdown(self):
        """Graceful shutdown"""
        self._running = False
        if self._portfolio.is_open:
            self._logger.warning("Closing positions on shutdown")
            self._execute_close_all()
        if self._connection:
            self._connection.disconnect()
        self._logger.info("System shutdown complete")
        self._print_summary()
    
    def _print_summary(self):
        """Print trading summary"""
        self._logger.info("=" * 60)
        self._logger.info("Trading Summary")
        self._logger.info(f"  Scalps: {self._signal_engine.signal_count if self._signal_engine else 0}")
        self._logger.info(f"  Realized PnL: {self._portfolio.realized_pnl:+.2f}")
        self._logger.info(f"  Log entries: {len(self._greeks_log)}")
        self._logger.info("=" * 60)


def main():
    """Entry point"""
    bot = GammaScalpingBot("config.yaml")
    
    if not bot.initialize():
        bot._logger.error("Initialization failed")
        return 1
    
    def signal_handler(sig, frame):
        bot._logger.info("Interrupt received, shutting down...")
        bot.shutdown()
        exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        pass
    finally:
        bot.shutdown()
    
    return 0


if __name__ == "__main__":
    main()
