from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is importable when run as part of the scripts package
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.core.config import get_settings  # noqa: E402
from selenium import webdriver
from selenium.webdriver.edge.options import Options as EdgeOptions

_EDGE_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
)


def make_driver() -> webdriver.Edge:
    """Return a headful Edge driver with anti-bot options."""
    binary = get_settings().browser_binary
    if not Path(binary).exists():
        raise RuntimeError(
            f"Microsoft Edge not found at '{binary}'. "
            "Set BROWSER_BINARY in your .env file."
        )
    opts = EdgeOptions()
    opts.binary_location = binary
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument(f"user-agent={_EDGE_UA}")
    return webdriver.Edge(options=opts)
