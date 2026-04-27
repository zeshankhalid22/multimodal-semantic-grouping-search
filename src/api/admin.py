from __future__ import annotations

import asyncio
import functools
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.core import database
from src.core.config import get_settings
from src.core.ingestion import IngestStatus, ingest_from_records

router = APIRouter(prefix="/admin", tags=["admin"])
_executor = ThreadPoolExecutor(max_workers=1)

# Ensure project root is on sys.path so scripts.* imports work
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_CONFIG_FILE = _ROOT / "Data" / "config.json"


class ExtractConfig(BaseModel):
    html_dir: str
    image_root: str = ""
    output_json: str = ""
    category: str | None = None
    platform: str = "amazon"
    include: list[str] = []
    exclude: list[str] = []
    max_attrs: int = 15


class DeleteRequest(BaseModel):
    json_file: str
    asins: list[str]


class IngestRequest(BaseModel):
    json_file: str


class AnalyzeRequest(BaseModel):
    json_file: str
    threshold: float = 0.5


class FilterRequest(BaseModel):
    json_file: str
    keep_attrs: list[str]


class SettingsBody(BaseModel):
    scraper_sleep: float = 2.0
    scraper_max_pages: int = 50
    browser_binary: str = ""
    analysis_threshold: int = 50
    max_attrs: int = 15
    default_platform: str = "amazon"
    data_dir: str = "Data"


def _read_json(path: str) -> list[dict]:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else []


def _write_json(path: str, data: list) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _default_config() -> dict[str, Any]:
    settings = get_settings()
    return {
        "scraper_sleep": 2.0,
        "scraper_max_pages": 50,
        "browser_binary": settings.browser_binary,
        "analysis_threshold": 50,
        "max_attrs": 15,
        "default_platform": "amazon",
        "data_dir": "Data",
    }


@router.get("/stats")
async def admin_stats() -> dict[str, Any]:
    try:
        return database.fetch_stats()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/data-categories")
async def admin_data_categories() -> dict[str, Any]:
    """List Data/ subfolders that have scraped HTML files ready for extraction."""
    data_dir = _ROOT / "Data"
    if not data_dir.is_dir():
        return {"categories": []}
    cats = []
    for d in sorted(data_dir.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        html_count = len(list(d.glob("*.html")))
        json_exists = (d / f"{d.name}.json").is_file()
        cats.append({"name": d.name, "html_count": html_count, "json_ready": json_exists})
    return {"categories": cats}


@router.post("/extract")
async def admin_extract(config: ExtractConfig) -> dict[str, Any]:
    html_dir = Path(config.html_dir)
    if not html_dir.is_dir():
        raise HTTPException(status_code=400, detail=f"HTML directory not found: '{config.html_dir}'")

    folder_name = html_dir.name
    image_root = Path(config.image_root) if config.image_root else None
    output_json = Path(config.output_json) if config.output_json else None
    category = config.category or None

    from scripts.amazon_extractor import _DEFAULT_EXCLUDE, extract_directory
    exclude = _DEFAULT_EXCLUDE | set(config.exclude)

    def _run() -> list[dict]:
        return extract_directory(
            html_dir=html_dir,
            output_json=output_json,
            image_root=image_root,
            category=category,
            platform=config.platform,
            include=config.include,
            exclude=exclude,
            max_attrs=config.max_attrs,
            no_images=False,
        )

    try:
        loop = asyncio.get_event_loop()
        products = await loop.run_in_executor(_executor, _run)
        actual_json = str(output_json) if output_json else str(html_dir / f"{folder_name}.json")
        return {"products": products, "output_json": actual_json}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/products")
async def admin_get_products(json_file: str) -> dict[str, Any]:
    try:
        return {"products": _read_json(json_file)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/products")
async def admin_delete_products(body: DeleteRequest) -> dict[str, Any]:
    try:
        kept = [p for p in _read_json(body.json_file) if p.get("asin") not in body.asins]
        _write_json(body.json_file, kept)
        return {"remaining": len(kept)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/ingest")
async def admin_ingest(body: IngestRequest) -> dict[str, Any]:
    products = _read_json(body.json_file)
    if not products:
        raise HTTPException(status_code=400, detail="No products in JSON file.")
    try:
        loop = asyncio.get_event_loop()
        summary = await loop.run_in_executor(
            _executor, functools.partial(ingest_from_records, products)
        )
        failures = [
            {"asin": r.asin, "reason": r.reason}
            for r in summary.results if r.status == IngestStatus.FAILED
        ]
        duplicates = [
            r.asin for r in summary.results if r.status == IngestStatus.SKIPPED_DUPLICATE
        ]
        if failures:
            log_path = Path(body.json_file).parent / "failed.log"
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(f"\n{'─'*40}\n{datetime.now().isoformat()}\n")
                for item in failures:
                    fh.write(f"ASIN : {item['asin']}\nError: {item['reason']}\n\n")
        return {
            "total": summary.total,
            "inserted": summary.inserted,
            "skipped_duplicate": summary.skipped_duplicate,
            "skipped_missing_image": summary.skipped_missing_image,
            "failed": summary.failed,
            "failures": failures,
            "duplicates": duplicates,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/image")
async def admin_image(path: str) -> FileResponse:
    p = Path(path)
    if not p.is_file():
        raise HTTPException(status_code=404, detail="Image not found.")
    return FileResponse(p)


@router.post("/analyze")
async def admin_analyze(body: AnalyzeRequest) -> dict[str, Any]:
    """Analyze attribute frequency across all products in the JSON file."""
    if not Path(body.json_file).is_file():
        raise HTTPException(status_code=400, detail=f"JSON file not found: '{body.json_file}'")
    if not (0.0 <= body.threshold <= 1.0):
        raise HTTPException(status_code=400, detail="threshold must be between 0 and 1.")
    try:
        from scripts.attribute_analysis import analyze_json, diagnose
        result = analyze_json(body.json_file, threshold=body.threshold)
        diag = diagnose(body.json_file)
        return {
            "total": result.total,
            "threshold": result.threshold,
            "all_attrs": result.all_attrs,
            "recommended": result.recommended,
            "diag": diag,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/filter")
async def admin_filter(body: FilterRequest) -> dict[str, Any]:
    """Rewrite the JSON keeping only the specified attribute keys inside each product."""
    if not Path(body.json_file).is_file():
        raise HTTPException(status_code=400, detail=f"JSON file not found: '{body.json_file}'")
    try:
        from scripts.attribute_analysis import filter_json
        count = filter_json(body.json_file, body.keep_attrs)
        return {"filtered": count, "json_file": body.json_file}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/settings")
async def admin_get_settings() -> dict[str, Any]:
    if _CONFIG_FILE.is_file():
        try:
            return json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return _default_config()


@router.post("/settings")
async def admin_save_settings(body: SettingsBody) -> dict[str, Any]:
    _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_FILE.write_text(
        json.dumps(body.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return {"ok": True}


@router.get("/db-products")
async def admin_db_products(
    category: str = "all",
    search: str = "",
    page: int = 1,
    limit: int = 48,
) -> dict[str, Any]:
    """List products from the database with pagination, category filter, and search."""
    offset = (page - 1) * limit
    srch = search.strip() or None
    try:
        products = database.fetch_products_by_category(
            category, limit=limit, offset=offset, search=srch
        )
        total = database.fetch_category_count(category, search=srch)
        cats = database.fetch_categories()
        return {
            "products": products,
            "total": total,
            "page": page,
            "limit": limit,
            "categories": cats,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/db-products/{asin}")
async def admin_delete_db_product(asin: str) -> dict[str, Any]:
    """Permanently delete a product from the database by ASIN."""
    try:
        deleted = database.delete_product_by_asin(asin)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"ASIN '{asin}' not found.")
        return {"deleted": True, "asin": asin}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
