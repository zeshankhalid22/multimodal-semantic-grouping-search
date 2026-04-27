from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

import lxml  # noqa: F401
import requests
from bs4 import BeautifulSoup

_PARSER = "lxml"


def _clean_text(text: str) -> str:
    """Remove invisible Unicode chars and collapse whitespace."""
    if not text:
        return ""
    text = re.sub(r"[\u200b\u200e\u200f\ufeff\u00a0]", " ", text)
    return " ".join(text.split()).strip()


def _clean_string(text: Any) -> str:
    """Normalise to ASCII, strip special chars, collapse whitespace."""
    if not isinstance(text, str):
        return str(text) if text is not None else ""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("utf-8")
    text = re.sub(r"[^a-zA-Z0-9\s.,\-'/&()]", "", text)
    return " ".join(text.split()).strip()


def _clean_key(text: str) -> str:
    """Normalise an attribute key to a clean, colon-free string."""
    text = re.sub(r"[\u200b\u200e\u200f\ufeff\u00a0]", " ", text)
    text = re.sub(r"[^a-zA-Z0-9\s]", "", text)
    return " ".join(text.split()).strip()


def _clean_price(raw: Any) -> float | None:
    """Return price as float or None."""
    if not raw or str(raw).strip() in ("", "N/A"):
        return None
    text = re.sub(r"[^\d\s.]", "", str(raw)).strip()
    m = re.search(r"(\d+)\s+(\d{2})$", text)
    if m:
        text = f"{m.group(1)}.{m.group(2)}"
    text = text.replace(" ", "")
    try:
        return float(text)
    except ValueError:
        return None


def _extract_asin(soup: BeautifulSoup) -> str | None:
    el = soup.find("input", id="ASIN")
    if el and el.get("value"):
        return el["value"].strip()
    link = soup.find("link", rel="canonical")
    if link and link.get("href"):
        m = re.search(r"/dp/([A-Z0-9]{10})", link["href"])
        if m:
            return m.group(1)
    return None


def _extract_title(soup: BeautifulSoup) -> str | None:
    el = soup.find("span", id="productTitle")
    return _clean_string(el.get_text()) if el else None


def _extract_price(soup: BeautifulSoup) -> float | None:
    selectors = [
        "#corePriceDisplay_desktop_feature_div .a-offscreen",
        "#corePrice_feature_div .a-offscreen",
        "span.a-price .a-offscreen",
    ]
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            text = _clean_text(el.get_text())
            if text:
                return _clean_price(text)
    return None


def _extract_description(soup: BeautifulSoup) -> str:
    parts: list[str] = []

    desc = soup.find("div", id="productDescription")
    if desc:
        text = _clean_string(desc.get_text())
        if text:
            parts.append(text)

    for container_id in (
        "feature-bullets",
        "featurebullets_feature_div",
        "productFactsDesktopExpander",
    ):
        container = soup.find("div", id=container_id)
        if container:
            for li in container.select("li span.a-list-item"):
                text = _clean_string(li.get_text())
                if text:
                    parts.append(text)
            break

    return " ".join(parts)


def _extract_image_url(soup: BeautifulSoup) -> str | None:
    """Try to get the highest-resolution image URL available."""
    img = soup.find("img", id="landingImage")
    if img:
        raw = img.get("data-a-dynamic-image")
        if raw:
            try:
                urls = json.loads(raw)
                if urls:
                    best = max(urls, key=lambda u: urls[u][0] * urls[u][1])
                    return best
            except (json.JSONDecodeError, TypeError, IndexError):
                pass
        if img.get("src"):
            return img["src"]

    for img_id in ("imgTagWrapperId", "imgBlkFront"):
        el = soup.find(id=img_id)
        if el:
            child = el.find("img") if el.name != "img" else el
            if child and child.get("src"):
                return child["src"]

    return None


def _extract_category_from_breadcrumb(soup: BeautifulSoup) -> str | None:
    """Return the leaf category from Amazon's wayfinding breadcrumb."""
    crumbs = soup.select("#wayfinding-breadcrumbs_feature_div li span.a-list-item a")
    if crumbs:
        leaf = _clean_string(crumbs[-1].get_text())
        return leaf.lower() if leaf else None
    return None


def _extract_raw_attributes(soup: BeautifulSoup) -> dict[str, str]:
    """Scrape all product detail attributes from tables and bullet lists."""
    attrs: dict[str, str] = {}

    wrapper_ids = [
        "detailBulletsWrapper_feature_div",
        "productDetails_feature_div",
        "productDetails_techSpec_section_1",
        "productDetails_detailBullets_sections1",
        "technicalSpecifications_feature_div",
    ]

    for wid in wrapper_ids:
        container = soup.find(id=wid)
        if not container:
            continue

        for row in container.select("tr"):
            th = row.find("th")
            td = row.find("td")
            if th and td:
                key = _clean_key(th.get_text())
                val = _clean_string(td.get_text())
                if key and val:
                    attrs.setdefault(key, val)

        for li in container.select("li"):
            bold = li.select_one(".a-text-bold")
            if bold:
                key = _clean_key(bold.get_text())
                full = _clean_string(li.get_text())
                val = full[len(_clean_string(bold.get_text())) :].lstrip(": ").strip()
                if key and val:
                    attrs.setdefault(key, val)

    return attrs


def _download_image(url: str, save_path: Path) -> bool:
    """Download image to save_path. Returns True on success."""
    try:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        resp = requests.get(url, timeout=15, stream=True)
        resp.raise_for_status()
        with save_path.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=8192):
                fh.write(chunk)
        return True
    except Exception as exc:
        print(f"    ⚠  Image download failed ({url!r}): {exc}")
        return False


# Attributes excluded by default (noisy / always present)
_DEFAULT_EXCLUDE: set[str] = {
    "customer reviews",
    "best sellers rank",
    "date first available",
    "shipping weight",
    "domestic shipping",
    "international shipping",
    "warranty support",
    "product warranty",
    "customer ratings by feature",
    "feedback",
    "asin",
}


def process_html(
    html_path: Path,
    *,
    category: str | None,
    image_root: Path | None,
    platform: str,
    include: list[str],
    exclude: set[str],
    max_attrs: int,
    no_images: bool,
) -> dict[str, Any] | None:
    """
    Parse one HTML file and return an ingester-compatible product dict,
    or None if the product should be skipped.
    """
    with html_path.open("r", encoding="utf-8", errors="replace") as fh:
        soup = BeautifulSoup(fh.read(), _PARSER)

    asin = _extract_asin(soup)
    if not asin:
        print(f"  ✗ {html_path.name}: could not extract ASIN — skipped")
        return None

    title = _extract_title(soup)
    if not title:
        print(f"  ✗ {html_path.name} ({asin}): could not extract title — skipped")
        return None

    resolved_category = category or _extract_category_from_breadcrumb(soup)
    if not resolved_category:
        print(f"  ✗ {html_path.name} ({asin}): could not determine category — skipped")
        return None

    raw_attrs = _extract_raw_attributes(soup)

    for required in include:
        if required not in raw_attrs:
            print(f"  ✗ {html_path.name} ({asin}): required attribute {required!r} not found — skipped")
            return None

    filtered_attrs: dict[str, str] = {}
    exclude_lower = {e.lower().replace("_", " ") for e in exclude}
    include_lower = {i.lower().replace("_", " ") for i in include}

    for key, val in raw_attrs.items():
        key_lower = key.lower()
        if key_lower in exclude_lower:
            continue
        if key_lower in include_lower:
            filtered_attrs[key] = val

    budget = max_attrs - len(filtered_attrs)
    for key, val in raw_attrs.items():
        if budget <= 0:
            break
        key_lower = key.lower()
        if key_lower not in exclude_lower and key not in filtered_attrs:
            filtered_attrs[key] = val
            budget -= 1

    image_url = _extract_image_url(soup)
    image_path_str: str | None = None

    if image_url and not no_images and image_root is not None:
        ext = Path(image_url.split("?")[0]).suffix or ".jpg"
        rel_path = Path(resolved_category) / f"{asin}{ext}"
        abs_path = image_root / rel_path
        if _download_image(image_url, abs_path):
            image_path_str = str(image_root / rel_path)
            print(f"  📥 {asin}: image saved → {image_path_str}")
        else:
            image_path_str = None
    elif image_url and no_images:
        image_path_str = image_url

    if not image_path_str:
        print(f"  ✗ {html_path.name} ({asin}): no image available — skipped")
        return None

    return {
        "asin": asin,
        "title": title,
        "price": _extract_price(soup),
        "description": _extract_description(soup),
        "platform": platform,
        "category": resolved_category,
        "image_path": image_path_str,
        "attributes": filtered_attrs,
    }


def extract_directory(
    html_dir: Path,
    output_json: Path | None = None,
    image_root: Path | None = None,
    *,
    category: str | None,
    platform: str,
    include: list[str],
    exclude: set[str],
    max_attrs: int,
    no_images: bool,
) -> list[dict]:
    """
    Process all .html files in html_dir.

    Auto-derives output_json, image_root, and category from html_dir if not provided.
    """
    folder_name = html_dir.name
    if not category:
        category = folder_name
    if image_root is None:
        image_root = html_dir / "images"
    if output_json is None:
        output_json = html_dir / f"{folder_name}.json"

    html_files = sorted(html_dir.glob("*.html"))
    if not html_files:
        print(f"No HTML files found in {html_dir}")
        return []

    print(f"Found {len(html_files)} HTML file(s) in {html_dir}\n")

    products: list[dict] = []
    skipped = 0

    for html_path in html_files:
        print(f"→ {html_path.name}")
        result = process_html(
            html_path,
            category=category,
            image_root=image_root,
            platform=platform,
            include=include,
            exclude=exclude,
            max_attrs=max_attrs,
            no_images=no_images,
        )
        if result:
            products.append(result)
            print(f"  ✓ {result['asin']} | {result['category']} | {result['title'][:60]}")
        else:
            skipped += 1

    output_json.parent.mkdir(parents=True, exist_ok=True)
    with output_json.open("w", encoding="utf-8") as fh:
        json.dump(products, fh, indent=2, ensure_ascii=False)

    print(f"\n{'─' * 52}")
    print(f"Extraction complete: {len(products)} extracted, {skipped} skipped → {output_json}")
    return products


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="amazon_extractor",
        description="Extract Amazon HTML product pages → ingester-compatible JSON.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--html-dir", required=True, metavar="DIR", help="Directory containing .html product files.")
    p.add_argument("--image-root", required=True, metavar="DIR", help="Root folder to save images under.")
    p.add_argument("--output-json", required=True, metavar="PATH", help="Output JSON file path.")
    p.add_argument("--category", default=None, metavar="NAME", help="Category name (overrides breadcrumb auto-detection).")
    p.add_argument("--platform", default="amazon", help="Platform label stored in each record.")
    p.add_argument("--include", nargs="*", default=[], help="Attribute keys that MUST be present.")
    p.add_argument("--exclude", nargs="*", default=[], help="Attribute keys to always omit.")
    p.add_argument("--max-attrs", type=int, default=15, metavar="N", help="Maximum number of secondary attributes to keep.")
    p.add_argument("--no-images", action="store_true", help="Skip image download; store image URL in image_path instead.")
    return p


def main() -> None:
    args = _build_parser().parse_args()

    html_dir = Path(args.html_dir)
    if not html_dir.is_dir():
        print(f"✗ --html-dir not found: {html_dir}", file=sys.stderr)
        sys.exit(1)

    exclude = _DEFAULT_EXCLUDE | set(args.exclude)

    extract_directory(
        html_dir=html_dir,
        output_json=Path(args.output_json),
        image_root=None if args.no_images else Path(args.image_root),
        category=args.category,
        platform=args.platform,
        include=args.include,
        exclude=exclude,
        max_attrs=args.max_attrs,
        no_images=args.no_images,
    )


if __name__ == "__main__":
    main()
