# files/broker/paper.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Literal, Any

import alpaca_trade_api as tradeapi

from files.config import load_alpaca_config
from files.utils.logger import get_logger

logger = get_logger(__name__)

StrategySide = Literal["LONG", "SHORT"]
AlpacaSide = Literal["buy", "sell"]


def _map_strategy_side_to_alpaca(side: StrategySide) -> AlpacaSide:
    if side == "LONG":
        return "buy"
    if side == "SHORT":
        return "sell"
    raise ValueError(f"Invalid strategy side: {side!r} (expected 'LONG' or 'SHORT')")


@dataclass(frozen=True)
class OpenPosition:
    symbol: str
    qty: float
    side: StrategySide


class PaperBroker:
    def __init__(self, *, dry_run: bool = False):
        self.dry_run = dry_run

        alp = load_alpaca_config()

        self.api = tradeapi.REST(
            alp.api_key,
            alp.secret_key,
            base_url=alp.base_url,
            api_version="v2",
        )

        logger.info(
            "PaperBroker initialized",
            extra={"dry_run": self.dry_run, "base_url": alp.base_url},
        )

    def get_position(self, symbol: str) -> Optional[Any]:
        try:
            return self.api.get_position(symbol)
        except tradeapi.rest.APIError:
            return None

    def open_position(self, *, symbol: str, side: StrategySide, size: float) -> None:
        if size <= 0:
            raise ValueError(f"size must be > 0. got {size}")

        # Guardrail: don't open if already in a position
        existing = self.get_position(symbol)
        if existing is not None:
            logger.warning(
                "Refusing to open: position already exists",
                extra={"symbol": symbol, "existing_qty": getattr(existing, "qty", None)},
            )
            return

        alpaca_side = _map_strategy_side_to_alpaca(side)

        if self.dry_run:
            logger.info(
                "DRY RUN: would submit order",
                extra={"symbol": symbol, "side": side, "alpaca_side": alpaca_side, "qty": size},
            )
            return

        logger.info(
            "Submitting order",
            extra={"symbol": symbol, "side": side, "alpaca_side": alpaca_side, "qty": size},
        )

        self.api.submit_order(
            symbol=symbol,
            qty=size,
            side=alpaca_side,
            type="market",
            time_in_force="gtc",
        )

    def close_position(self, *, symbol: str) -> None:
        if self.dry_run:
            logger.info("DRY RUN: would close position", extra={"symbol": symbol})
            return

        pos = self.get_position(symbol)
        if pos is None:
            logger.info("No position to close", extra={"symbol": symbol})
            return

        logger.info(
            "Closing position",
            extra={"symbol": symbol, "qty": getattr(pos, "qty", None)},
        )
        self.api.close_position(symbol)


