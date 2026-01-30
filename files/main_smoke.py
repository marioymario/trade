# files/main_smoke.py
from __future__ import annotations

from files.config import load_trading_config, load_alpaca_config
from files.broker.paper import PaperBroker
from files.utils.logger import get_logger

logger = get_logger(__name__)


def main() -> None:
    tcfg = load_trading_config()
    _ = load_alpaca_config()  # validates env keys

    broker = PaperBroker(dry_run=True)

    logger.info("✅ Smoke OK: config loaded, alpaca env present, broker constructed")
    logger.info(f"symbol={tcfg.symbol} timeframe={tcfg.timeframe}")


if __name__ == "__main__":
    main()

