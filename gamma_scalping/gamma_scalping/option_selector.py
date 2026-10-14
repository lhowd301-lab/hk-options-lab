"""Option contract selector engine"""

import datetime
import logging
from typing import List, Optional

import pandas as pd
from futu import (
    OpenQuoteContext, OptionType, OptionCondType,
    OptionDataFilter, RET_OK,
)

from .config import Config
from .models import OptionContract, OptionSide

logger = logging.getLogger("GammaScalping.OptionSelector")


class OptionSelector:
    """Select optimal option contract based on selection rules"""

    def __init__(self, quote_ctx: OpenQuoteContext, config: Config):
        self._ctx = quote_ctx
        self._cfg = config
        self._last_chain: List[OptionContract] = []
        self._selected_contract: Optional[OptionContract] = None

    def fetch_option_chain(self) -> List[OptionContract]:
        """Fetch and filter option chain"""
        futu_opt_type = OptionType.CALL if self._cfg.option_type == "CALL" else OptionType.PUT

        logger.info("Query option chain: " + self._cfg.underlying_code + " type=" + self._cfg.option_type)

        ret, data = self._ctx.get_option_chain(
            code=self._cfg.underlying_code,
            option_type=futu_opt_type,
            option_cond_type=OptionCondType.ALL,
        )

        if ret != RET_OK:
            logger.error("Failed to get option chain: " + str(data))
            return []

        if data is None or len(data) == 0:
            logger.error("Empty option chain")
            return []

        # Local filter by DTE and Delta
        import datetime as dt
        today = dt.date.today()
        import pandas as pd
        filtered_idx = []
        for idx, row in data.iterrows():
            expire = dt.datetime.strptime(str(row["strike_time"]), "%Y-%m-%d").date()
            dte = (expire - today).days
            if self._cfg.expiry_min_days <= dte <= self._cfg.expiry_max_days:
                filtered_idx.append(idx)

        if filtered_idx:
            filtered = data.loc[filtered_idx]
        else:
            logger.warning("No contracts matching DTE " + str(self._cfg.expiry_min_days) + "-" + str(self._cfg.expiry_max_days))
            filtered = data

        contracts = self._enrich_with_greeks(filtered)
        self._last_chain = contracts
        return contracts
    def _enrich_with_greeks(self, chain_df):
        """Enrich contracts with Greek values from API"""
        from futu import OptionStrategyLeg, StrategyLegAction

        contracts = []
        codes = list(chain_df["code"])

        def safe_float(v, default=0.0):
            try:
                if v is None: return default
                s = str(v).strip()
                return float(s) if s and s.upper() != "N/A" else default
            except (ValueError, TypeError):
                return default

        for code in codes:
            leg = OptionStrategyLeg()
            leg.code = code
            leg.quantity = 1
            leg.action = StrategyLegAction.UNKNOWN

            ret, qdata = self._ctx.get_option_quote([leg])
            if ret != 0 or qdata is None or len(qdata) == 0:
                continue

            row = qdata.iloc[0]
            delta_v = safe_float(row.get("delta", 0))
            if abs(delta_v) < 0.01:
                continue

            try:
                from .models import OptionSide
                opt_side = OptionSide.CALL
                raw_type = str(row.get("option_type", ""))
                if raw_type.upper() == "PUT":
                    opt_side = OptionSide.PUT
                expire_str = str(row.get("expire_time", ""))
                expire_date = datetime.datetime.strptime(expire_str, "%Y-%m-%d").date()

                contract = OptionContract(
                    code=code,
                    name=str(row.get("name", "")),
                    option_type=opt_side,
                    strike_price=safe_float(row.get("strike_price", 0)),
                    expiry_date=expire_date,
                    days_to_expiry=int(row.get("days_to_expiry", 0) or 0),
                    delta=delta_v,
                    gamma=safe_float(row.get("gamma", 0)),
                    theta=safe_float(row.get("theta", 0)),
                    vega=safe_float(row.get("vega", 0)),
                    implied_volatility=safe_float(row.get("implied_volatility", 0)),
                    last_price=safe_float(row.get("price", 0)),
                    bid_price=safe_float(row.get("bid_price", 0)),
                    ask_price=safe_float(row.get("ask_price", 0)),
                )
                if abs(contract.delta) > 0.01:
                    contracts.append(contract)
            except Exception as e:
                pass

        self._last_chain = contracts
        n = str(len(contracts))
        logger.info("Found " + n + " matching option contracts")
        return contracts
        def safe_float(v, default=0.0):
            try:
                if v is None: return default
                s = str(v).strip()
                return float(s) if s and s.upper() != "N/A" else default
            except (ValueError, TypeError):
                return default

        quote_iter = all_quotes.iterrows()
        for q_idx, (_, row) in enumerate(quote_iter):
            try:
                contract = OptionContract(
                    code=all_codes[q_idx] if q_idx < len(all_codes) else row.get("code", ""),
                    name=row.get("name", ""),
                    option_type=OptionSide.CALL if str(row.get("option_type", "")).upper() == "CALL" else OptionSide.PUT,
                    strike_price=safe_float(row.get("strike_price", 0)),
                    expiry_date=datetime.datetime.strptime(
                        str(row.get("expire_time", "")), "%Y-%m-%d"
                    ).date(),
                    days_to_expiry=int(row.get("days_to_expiry", 0)),
                    delta=safe_float(row.get("delta", 0)),
                    gamma=safe_float(row.get("gamma", 0)),
                    theta=safe_float(row.get("theta", 0)),
                    vega=safe_float(row.get("vega", 0)),
                    implied_volatility=safe_float(row.get("implied_volatility", 0)),
                    last_price=safe_float(row.get("price", 0)),
                    bid_price=safe_float(row.get("bid_price", 0)),
                    ask_price=safe_float(row.get("ask_price", 0)),
                )
                if abs(contract.delta) > 0.01:
                    contracts.append(contract)
            except (ValueError, KeyError, TypeError) as e:
                logger.warning("Failed to parse contract: " + str(e))

        logger.info("Found " + str(len(contracts)) + " matching option contracts")
        return contracts

    def select_best_contract(self, contracts=None):
        """Select the best contract from candidates"""
        if contracts is None:
            contracts = self._last_chain
        if not contracts:
            contracts = self.fetch_option_chain()
        if not contracts:
            return None

        scored = []
        for c in contracts:
            delta_score = 1.0 - abs(abs(c.delta) - 0.5) / 0.5
            spread = abs(c.ask_price - c.bid_price) if c.ask_price > 0 and c.bid_price > 0 else 0.5
            liquidity_score = max(0, 1.0 - spread / (c.last_price * 0.1)) if c.last_price > 0 else 0.5
            total_score = delta_score * 0.6 + liquidity_score * 0.4
            scored.append((total_score, c))

        scored.sort(key=lambda x: -x[0])
        best = scored[0][1]

        logger.info(
            "Selected: " + best.code
            + " Strike=" + str(best.strike_price)
            + " Delta=" + str(round(best.delta, 4))
        )

        self._selected_contract = best
        return best

    @property
    def selected_contract(self):
        return self._selected_contract

    @property
    def last_chain(self):
        return self._last_chain
