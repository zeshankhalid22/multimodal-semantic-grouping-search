from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.core.config import get_settings

router = APIRouter(prefix="/scraper", tags=["scraper"])

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_QUERIES_FILE = _ROOT / "Data" / "queries.json"
_DEFAULT_QUERIES: dict[str, list[str]] = {
    "Bags": [
        "women leather tote bags",
        "men laptop backpacks",
        "crossbody bags for women",
    ],
    "Shoes": [
        "men athletic running shoes",
        "women casual sneakers",
        "women ankle boots",
    ],
    "Watches": [
        "men casual analog watch",
        "women gold watch",
    ],
    "Jackets": [
        "men leather jacket",
        "women faux leather jacket",
        "men bomber jacket",
    ],
}


def _load_queries() -> dict[str, list[str]]:
    if _QUERIES_FILE.is_file():
        try:
            return json.loads(_QUERIES_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return _DEFAULT_QUERIES.copy()


def _save_queries(queries: dict[str, list[str]]) -> None:
    _QUERIES_FILE.parent.mkdir(parents=True, exist_ok=True)
    _QUERIES_FILE.write_text(
        json.dumps(queries, indent=2, ensure_ascii=False), encoding="utf-8"
    )


@router.get("/queries")
def get_queries() -> dict[str, list[str]]:
    """Get the current set of search queries."""
    return _load_queries()


class QueriesBody(BaseModel):
    queries: dict[str, list[str]]


@router.post("/queries")
def save_queries(body: QueriesBody) -> dict[str, Any]:
    """Save a new set of search queries."""
    _save_queries(body.queries)
    return {"ok": True, "categories": len(body.queries)}


@router.get("/health")
def scraper_health() -> dict[str, Any]:
    """Check whether the browser binary is available for scraping."""
    binary = get_settings().browser_binary
    ok = Path(binary).exists()
    return {"ok": ok, "binary": binary, "status": "ready" if ok else "missing"}


class SearchBody(BaseModel):
    queries: dict[str, list[str]] | None = None
    data_dir: str = "Data"
    sleep: float = 2.0
    csv_file: str = "final_product_data.csv"


class FilterProductsBody(BaseModel):
    products: list[dict[str, Any]]
    remove_asins: list[str] | None = None
    csv_file: str = "final_product_data.csv"


@router.post("/search")
def run_search(body: SearchBody) -> dict[str, Any]:
    """
    Run the search phase: find products on Amazon and save listing card HTMLs.

    Uses CSV file to track already-scraped ASINs and prevent duplicates.
    """
    from scripts.amazon_scraper.scrape import search_products

    queries = body.queries if body.queries is not None else _load_queries()
    if not queries:
        raise HTTPException(status_code=400, detail="No queries defined.")

    try:
        products = search_products(
            queries,
            data_dir=body.data_dir,
            sleep=body.sleep,
            csv_file=body.csv_file,
        )

        unique_products = []
        seen_asins: set[str] = set()
        for p in products:
            if p["asin"] not in seen_asins:
                seen_asins.add(p["asin"])
                unique_products.append(p)

        return {"products": unique_products, "count": len(unique_products)}
    except Exception as exc:
        err_detail = f"{str(exc)}\n{traceback.format_exc()}"
        print(f"Search failed: {err_detail}")
        raise HTTPException(status_code=500, detail=err_detail)


class FilterBody(BaseModel):
    products: list[dict[str, Any]]
    selected_asins: list[str] | None = None
    remove_asins: list[str] | None = None


class ScrapeBody(BaseModel):
    products: list[dict[str, Any]]
    data_dir: str = "data_details"
    sleep: float = 3.0


@router.post("/filter")
def filter_products(body: FilterBody) -> dict[str, Any]:
    """
    Filter products before detail scraping.

    If selected_asins is provided, keep only those ASINs.
    If remove_asins is provided, exclude those ASINs.
    If both are None, return all products.
    """
    if not body.products:
        raise HTTPException(status_code=400, detail="No products provided.")

    filtered = body.products.copy()

    if body.selected_asins:
        selected_set = set(body.selected_asins)
        filtered = [p for p in filtered if p.get("asin") in selected_set]

    if body.remove_asins:
        remove_set = set(body.remove_asins)
        filtered = [p for p in filtered if p.get("asin") not in remove_set]

    return {
        "original_count": len(body.products),
        "filtered_count": len(filtered),
        "removed_count": len(body.products) - len(filtered),
        "products": filtered,
    }


@router.post("/scrape")
def run_scrape(body: ScrapeBody) -> dict[str, Any]:
    """
    Run the scrape phase: visit product detail pages and save full HTMLs.

    Takes the output of /search. Skips products that have already been scraped.
    """
    from scripts.amazon_scraper.scrape_details import scrape_product_pages

    if not body.products:
        raise HTTPException(status_code=400, detail="No products selected.")

    try:
        return scrape_product_pages(
            body.products, data_dir=body.data_dir, sleep=body.sleep
        )
    except Exception as exc:
        err_detail = f"{str(exc)}\n{traceback.format_exc()}"
        print(f"Scrape failed: {err_detail}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/files")
def list_scraped_files(data_dir: str = "Data") -> dict[str, Any]:
    """List all scraped HTML files organized by category."""
    base = _ROOT / data_dir
    if not base.is_dir():
        return {"categories": {}, "total": 0}

    categories: dict[str, list[str]] = {}
    for cat_dir in sorted(base.iterdir()):
        if not cat_dir.is_dir() or cat_dir.name.startswith("."):
            continue
        html_files = sorted(f.name for f in cat_dir.glob("*.html"))
        if html_files:
            categories[cat_dir.name] = html_files

    return {"categories": categories, "total": sum(len(v) for v in categories.values())}
