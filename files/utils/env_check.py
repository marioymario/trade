# files/utils/env_check.py
from __future__ import annotations

import os
from typing import Iterable


def require_env(keys: Iterable[str]) -> None:
    """
    Fail fast if required environment variables are missing.
    Never prints secret values.
    """
    missing = [k for k in keys if not os.getenv(k)]
    if missing:
        raise RuntimeError(
            "Missing required environment variables: "
            + ", ".join(missing)
            + ". Check your .env and how you run Docker Compose."
        )


def verify_alpaca_env() -> None:
    require_env(["ALPACA_API_KEY", "ALPACA_SECRET_KEY"])

