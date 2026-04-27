from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Generator

import psycopg2
from pgvector.psycopg2 import register_vector
from psycopg2 import pool

from src.core.config import get_settings

_pool: pool.ThreadedConnectionPool | None = None


def init_pool() -> None:
    """Initialize the threaded connection pool. Call once at app startup."""
    global _pool
    if _pool is not None:
        return
    settings = get_settings()
    _pool = pool.ThreadedConnectionPool(
        minconn=2,
        maxconn=10,
        **settings.db_dsn,
    )


def close_pool() -> None:
    """Close all connections in the pool. Call at app shutdown."""
    global _pool
    if _pool:
        _pool.closeall()
        _pool = None


@contextmanager
def get_conn() -> Generator[psycopg2.extensions.connection, None, None]:
    """Context manager that checks out a connection and auto-returns it to the pool."""
    if _pool is None:
        raise RuntimeError("Connection pool is not initialized. Call init_pool() first.")
    try:
        conn = _pool.getconn()
    except pool.PoolError as exc:
        raise RuntimeError(f"Could not acquire a DB connection: {exc}") from exc
    try:
        register_vector(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


def fetch_categories() -> list[str]:
    """Return all distinct category_group values, sorted alphabetically."""
    sql = """
        SELECT DISTINCT category_group
        FROM product_inventory
        ORDER BY category_group
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return [row[0] for row in cur.fetchall()]


def fetch_stats() -> dict[str, Any]:
    """Return aggregate counts for the admin dashboard."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*), COUNT(DISTINCT category_group), COUNT(DISTINCT platform) "
                "FROM product_inventory"
            )
            total, cat_count, plat_count = cur.fetchone()

            cur.execute(
                "SELECT platform, COUNT(*) AS n FROM product_inventory "
                "GROUP BY platform ORDER BY n DESC"
            )
            platforms = [{"name": r[0], "count": r[1]} for r in cur.fetchall()]

            cur.execute(
                "SELECT category_group, COUNT(*) AS n FROM product_inventory "
                "GROUP BY category_group ORDER BY n DESC"
            )
            categories = [{"name": r[0], "count": r[1]} for r in cur.fetchall()]

    return {
        "total": total,
        "category_count": cat_count,
        "platform_count": plat_count,
        "platforms": platforms,
        "categories": categories,
    }


def fetch_category_count(category: str, search: str | None = None) -> int:
    """Return total product count, optionally filtered by category and title search."""
    all_cats = category == "all"
    if search:
        if all_cats:
            sql = "SELECT COUNT(*) FROM product_inventory WHERE COALESCE(full_metadata->>'title','') ILIKE %s"
            params: tuple = (f"%{search}%",)
        else:
            sql = (
                "SELECT COUNT(*) FROM product_inventory "
                "WHERE category_group = %s AND COALESCE(full_metadata->>'title','') ILIKE %s"
            )
            params = (category, f"%{search}%")
    else:
        if all_cats:
            sql = "SELECT COUNT(*) FROM product_inventory"
            params = ()
        else:
            sql = "SELECT COUNT(*) FROM product_inventory WHERE category_group = %s"
            params = (category,)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return row[0] if row is not None else 0


def fetch_products_by_category(
    category: str,
    limit: int = 48,
    offset: int = 0,
    search: str | None = None,
) -> list[dict[str, Any]]:
    """Return a paginated list of product cards, optionally filtered by title search."""
    all_cats = category == "all"
    base = """
        SELECT id, image_path,
               full_metadata->>'title' AS title,
               full_metadata->>'price' AS price,
               full_metadata->>'asin'  AS asin
        FROM product_inventory
    """
    if search:
        where = "WHERE COALESCE(full_metadata->>'title','') ILIKE %s" if all_cats \
               else "WHERE category_group = %s AND COALESCE(full_metadata->>'title','') ILIKE %s"
        params: tuple = (f"%{search}%", limit, offset) if all_cats \
                        else (category, f"%{search}%", limit, offset)
    else:
        where = "" if all_cats else "WHERE category_group = %s"
        params = (limit, offset) if all_cats else (category, limit, offset)

    sql = f"{base} {where} ORDER BY id LIMIT %s OFFSET %s"

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    return [
        {
            "id": row[0],
            "image_path": row[1],
            "title": row[2] or "Untitled",
            "price": row[3],
            "asin": row[4] or "",
        }
        for row in rows
    ]


def fetch_product_by_id(product_id: int) -> dict[str, Any] | None:
    """Return full details for a single product, or None if not found."""
    sql = """
        SELECT
            id,
            platform,
            category_group,
            image_path,
            full_metadata
        FROM product_inventory
        WHERE id = %s
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (product_id,))
            row = cur.fetchone()

    if row is None:
        return None

    metadata: dict = row[4] or {}
    return {
        "id": row[0],
        "platform": row[1],
        "category_group": row[2],
        "image_path": row[3],
        "title": metadata.get("title", "Untitled"),
        "description": metadata.get("description", ""),
        "price": metadata.get("price"),
        "attributes": metadata.get("attributes") or {},
    }


def fetch_anchor_for_compare(product_id: int) -> dict[str, Any] | None:
    """Fetch the minimal fields needed to build a fusion embedding for a product."""
    sql = """
        SELECT
            id,
            image_path,
            category_group,
            full_metadata->>'title' AS title
        FROM product_inventory
        WHERE id = %s
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (product_id,))
            row = cur.fetchone()

    if row is None:
        return None

    return {
        "id": row[0],
        "image_path": row[1],
        "category_group": row[2],
        "title": row[3] or "",
    }


def fetch_similar_products(
    query_vector: list[float],
    category_group: str,
    exclude_id: int,
    limit: int = 5,
    ef_search: int = 40,
) -> list[dict[str, Any]]:
    """Run an HNSW cosine-similarity search and return the top-N similar products."""
    vector_literal = "[" + ",".join(str(v) for v in query_vector) + "]"

    sql = """
        SELECT
            id,
            platform,
            category_group,
            image_path,
            full_metadata,
            1 - (product_signature <=> %s::vector) AS similarity
        FROM product_inventory
        WHERE category_group = %s
          AND id != %s
        ORDER BY product_signature <=> %s::vector
        LIMIT %s
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SET hnsw.ef_search = {int(ef_search)};")
            cur.execute(
                sql,
                (vector_literal, category_group, exclude_id, vector_literal, limit),
            )
            rows = cur.fetchall()

    results = []
    for row in rows:
        metadata: dict = row[4] or {}
        results.append(
            {
                "id": row[0],
                "platform": row[1],
                "category_group": row[2],
                "image_path": row[3],
                "title": metadata.get("title", "Untitled"),
                "description": metadata.get("description", ""),
                "price": metadata.get("price"),
                "attributes": metadata.get("attributes") or {},
                "similarity": round(float(row[5]), 4),
            }
        )

    return results


def delete_product_by_asin(asin: str) -> bool:
    """Hard-delete a product row by ASIN. Returns True if a row was removed."""
    sql = "DELETE FROM product_inventory WHERE full_metadata->>'asin' = %s"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (asin,))
            return cur.rowcount > 0
