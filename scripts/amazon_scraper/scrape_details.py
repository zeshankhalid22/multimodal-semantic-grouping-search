from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from scripts.amazon_scraper._driver import make_driver


def scrape_product_pages(
    products: list[dict[str, Any]],
    data_dir: str = "Data",
    sleep: float = 3.0,
) -> dict[str, Any]:
    """
    Scrape the full product detail page for each item in products.

    Each item must have at minimum: {asin, category}.
    Optional: {link} — falls back to https://www.amazon.com/dp/<asin>.
    Saves full page HTML to Data/<category>/<asin>.html. Skips existing files.

    Returns:
        Dict with {saved, skipped, failed, files} counts and details.
    """
    base = Path(data_dir)
    saved = skipped = failed = 0
    files: list[dict[str, Any]] = []

    if not products:
        return {"saved": 0, "skipped": 0, "failed": 0, "files": []}

    driver = make_driver()

    try:
        for p in products:
            asin: str = p.get("asin") or ""
            category: str = p.get("category") or "default"
            link: str = p.get("link") or f"https://www.amazon.com/dp/{asin}"

            if not asin:
                failed += 1
                continue

            out_dir = base / f"{category}_details"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{asin}_details.html"

            if out_path.exists():
                skipped += 1
                files.append({"asin": asin, "path": str(out_path), "status": "skipped"})
                print(f"  Skip (exists): {asin}")
                continue

            try:
                driver.get(link)
                time.sleep(sleep)
                out_path.write_text(driver.page_source, encoding="utf-8")
                saved += 1
                files.append({"asin": asin, "path": str(out_path), "status": "saved"})
                print(f"  Saved: {asin} → {out_path}")
            except Exception as exc:
                failed += 1
                files.append({"asin": asin, "path": "", "status": f"failed: {exc}"})
                print(f"  Failed: {asin}: {exc}")

    finally:
        driver.quit()

    print(f"Detail scrape complete — saved:{saved}  skipped:{skipped}  failed:{failed}")
    return {"saved": saved, "skipped": skipped, "failed": failed, "files": files}
