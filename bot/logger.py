import logging
from pathlib import Path

from bot.config import LoggingConfig


def setup_logging(config: LoggingConfig) -> None:
    log_path = Path(config.file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, config.level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_path),
        ],
    )

    # ccxt/aiohttp warn about "unclosed session" when an exchange never
    # connected in the first place (e.g. no internet) — purely cosmetic
    # noise on top of the clear message the bot already logs itself.
    logging.getLogger("ccxt.base.exchange").setLevel(logging.CRITICAL)
    logging.getLogger("asyncio").setLevel(logging.CRITICAL)
