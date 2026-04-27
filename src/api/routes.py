from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from src.core import database, ml_model
from src.core.config import get_settings

router = APIRouter()


@router.get("/categories", response_class=JSONResponse)
async def get_categories() -> list[str]:
    """Return all distinct category_group values, sorted alphabetically."""
    try:
        return database.fetch_categories()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/products", response_class=JSONResponse)
async def get_products(
    category: str = Query(..., description="category_group filter"),
    limit: int = Query(default=48, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    page: int | None = Query(default=None, ge=1, description="1-based page number"),
    search: str | None = Query(default=None, description="Case-insensitive title search"),
) -> dict[str, Any]:
    """Paginated gallery feed with optional title search."""
    search_clean = (search or "").strip() or None

    if page is not None and offset != 0:
        raise HTTPException(status_code=400, detail="Use either `page` or `offset`, not both.")

    resolved_offset = (page - 1) * limit if page is not None else offset
    resolved_page = page if page is not None else (resolved_offset // limit) + 1

    try:
        total = database.fetch_category_count(category, search=search_clean)

        if total > 0 and resolved_offset >= total:
            raise HTTPException(
                status_code=400,
                detail=f"Requested page is out of range. total={total}, offset={resolved_offset}.",
            )

        products = database.fetch_products_by_category(
            category=category,
            limit=limit,
            offset=resolved_offset,
            search=search_clean,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "category": category,
        "search": search_clean,
        "limit": limit,
        "offset": resolved_offset,
        "page": resolved_page,
        "total": total,
        "count": len(products),
        "products": products,
    }


@router.get("/product/{product_id}", response_class=JSONResponse)
async def get_product(product_id: int) -> dict[str, Any]:
    """Return the full metadata for a single product."""
    try:
        product = database.fetch_product_by_id(product_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if product is None:
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found.")

    return product


@router.get("/product/{product_id}/compare", response_class=JSONResponse)
async def compare_product(
    product_id: int,
    limit: int = Query(default=5, ge=1, le=20, description="Number of similar products per page."),
    page: int = Query(default=1, ge=1, description="1-based page number."),
) -> dict[str, Any]:
    """
    Generate a fused embedding for the anchor product and return the most similar
    products within the same category via HNSW cosine-similarity search.

    Paging: pgvector doesn't support OFFSET on HNSW scans, so we fetch
    (page * limit) rows and slice in Python.
    """
    settings = get_settings()

    try:
        anchor_raw = database.fetch_anchor_for_compare(product_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if anchor_raw is None:
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found.")

    image_root = settings.image_root
    full_image_path = (
        os.path.join(image_root, anchor_raw["image_path"])
        if image_root
        else anchor_raw["image_path"]
    )

    if not os.path.isfile(full_image_path):
        raise HTTPException(
            status_code=422,
            detail=f"Image not found at {full_image_path!r}. Check IMAGE_ROOT in your .env file.",
        )

    try:
        query_vector = ml_model.generate_fused_embedding(
            image_path=anchor_raw["image_path"],
            title=anchor_raw["title"],
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Embedding error: {exc}") from exc

    fetch_n = page * limit
    try:
        similar_raw = database.fetch_similar_products(
            query_vector=query_vector,
            category_group=anchor_raw["category_group"],
            exclude_id=product_id,
            limit=fetch_n,
            ef_search=settings.hnsw_ef_search,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    db_offset = (page - 1) * limit
    similar_page = similar_raw[db_offset : db_offset + limit]

    try:
        anchor = database.fetch_product_by_id(product_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "anchor": anchor,
        "similar": similar_page,
        "page": page,
        "limit": limit,
        "total_fetched": len(similar_raw),
    }
