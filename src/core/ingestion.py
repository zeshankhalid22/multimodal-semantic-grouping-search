from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import psycopg2

from src.core import database, ml_model
from src.core.config import get_settings


class IngestStatus(str, Enum):
    INSERTED = "inserted"
    SKIPPED_DUPLICATE = "skipped_duplicate"
    SKIPPED_MISSING_IMAGE = "skipped_missing_image"
    SKIPPED_INVALID = "skipped_invalid"
    FAILED = "failed"


@dataclass
class IngestResult:
    asin: str
    status: IngestStatus
    reason: str = ""


@dataclass
class IngestSummary:
    total: int = 0
    inserted: int = 0
    skipped_duplicate: int = 0
    skipped_missing_image: int = 0
    skipped_invalid: int = 0
    failed: int = 0
    results: list[IngestResult] = field(default_factory=list)

    def add(self, result: IngestResult) -> None:
        self.total += 1
        self.results.append(result)
        match result.status:
            case IngestStatus.INSERTED:
                self.inserted += 1
            case IngestStatus.SKIPPED_DUPLICATE:
                self.skipped_duplicate += 1
            case IngestStatus.SKIPPED_MISSING_IMAGE:
                self.skipped_missing_image += 1
            case IngestStatus.SKIPPED_INVALID:
                self.skipped_invalid += 1
            case IngestStatus.FAILED:
                self.failed += 1


_MANDATORY_FIELDS = ("asin", "title", "image_path")

_SQL_EXISTS = "SELECT 1 FROM product_inventory WHERE full_metadata->>'asin' = %s LIMIT 1"

_SQL_INSERT = """
    INSERT INTO product_inventory
        (platform, category, image_path, full_metadata, category_group, product_signature)
    VALUES
        (%s, %s, %s, %s::jsonb, %s, %s::vector)
"""


def _resolve_image_path(image_path: str, image_root: str) -> str:
    if image_root:
        return os.path.join(image_root, image_path)
    return image_path


def _parse_price(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _build_full_metadata(record: dict[str, Any], price: float | None) -> dict[str, Any]:
    return {
        "asin": record["asin"],
        "title": record["title"],
        "image_path": record["image_path"],
        "category": record.get("category") or "",
        "platform": record.get("platform") or "",
        "price": price,
        "description": record.get("description") or "",
        "attributes": record.get("attributes") or {},
    }


def _asin_exists(asin: str) -> bool:
    with database.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(_SQL_EXISTS, (asin,))
            return cur.fetchone() is not None


def _insert_product(
    record: dict[str, Any],
    category_group: str,
    full_metadata: dict[str, Any],
    embedding: list[float],
) -> None:
    platform: str = record.get("platform") or "unknown"
    image_path: str = record["image_path"]
    category_group_db = category_group[:20]  # VARCHAR(20) schema constraint
    vector_literal = "[" + ",".join(str(v) for v in embedding) + "]"
    metadata_json = json.dumps(full_metadata)

    with database.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                _SQL_INSERT,
                (platform, category_group_db, image_path, metadata_json, category_group_db, vector_literal),
            )


def ingest_record(
    record: dict[str, Any],
    image_root: str = "",
    dry_run: bool = False,
) -> IngestResult:
    """Validate and ingest a single product record."""
    settings = get_settings()
    effective_image_root = image_root or settings.image_root or ""

    missing = [f for f in _MANDATORY_FIELDS if not record.get(f)]
    if missing:
        asin = record.get("asin") or "<unknown>"
        return IngestResult(
            asin=asin,
            status=IngestStatus.SKIPPED_INVALID,
            reason=f"Missing mandatory fields: {', '.join(missing)}",
        )

    asin: str = record["asin"]
    title: str = record["title"]
    image_path: str = record["image_path"]

    category_group: str = (record.get("category") or "").strip() or "default"

    full_image_path = _resolve_image_path(image_path, effective_image_root)
    if not os.path.isfile(full_image_path):
        return IngestResult(
            asin=asin,
            status=IngestStatus.SKIPPED_MISSING_IMAGE,
            reason=f"Image not found: {full_image_path!r}",
        )

    if dry_run:
        return IngestResult(
            asin=asin,
            status=IngestStatus.INSERTED,
            reason=f"[dry-run] category_group={category_group!r}, image OK",
        )

    if _asin_exists(asin):
        return IngestResult(
            asin=asin,
            status=IngestStatus.SKIPPED_DUPLICATE,
            reason="asin already exists in product_inventory",
        )

    try:
        embedding = ml_model.generate_fused_embedding(
            image_path=full_image_path,
            title=title,
        )
    except Exception as exc:
        return IngestResult(asin=asin, status=IngestStatus.FAILED, reason=f"Embedding error: {exc}")

    price = _parse_price(record.get("price"))
    full_metadata = _build_full_metadata(record, price)

    try:
        _insert_product(record, category_group, full_metadata, embedding)
    except psycopg2.Error as exc:
        return IngestResult(asin=asin, status=IngestStatus.FAILED, reason=f"DB error: {exc}")

    return IngestResult(asin=asin, status=IngestStatus.INSERTED)


def ingest_from_records(
    records: list[dict[str, Any]],
    image_root: str = "",
    dry_run: bool = False,
    limit: int | None = None,
    progress_callback: Any = None,
) -> IngestSummary:
    """Ingest a list of product records and return an aggregate summary."""
    summary = IngestSummary()
    batch = records[:limit] if limit is not None else records

    for record in batch:
        result = ingest_record(record, image_root=image_root, dry_run=dry_run)
        summary.add(result)
        if progress_callback is not None:
            progress_callback(result)

    if not dry_run and summary.inserted > 0:
        try:
            with database.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("ANALYZE product_inventory")
        except Exception:
            pass  # non-critical

    return summary


def ingest_from_file(
    json_path: str | Path,
    image_root: str = "",
    dry_run: bool = False,
    limit: int | None = None,
    progress_callback: Any = None,
) -> IngestSummary:
    """
    Load a JSON file (top-level array) and ingest all product records.

    Raises:
        FileNotFoundError: If the JSON file does not exist.
        ValueError: If the JSON is not a top-level list.
    """
    json_path = Path(json_path)
    if not json_path.is_file():
        raise FileNotFoundError(f"JSON file not found: {json_path}")

    with json_path.open(encoding="utf-8") as fh:
        data = json.load(fh)

    if not isinstance(data, list):
        raise ValueError(
            f"Expected a JSON array at the top level of {json_path}, got {type(data).__name__}."
        )

    return ingest_from_records(
        records=data,
        image_root=image_root,
        dry_run=dry_run,
        limit=limit,
        progress_callback=progress_callback,
    )
