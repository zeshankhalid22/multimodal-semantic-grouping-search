from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MANDATORY_TOP_LEVEL = {
    "asin", "title", "price", "description",
    "image_path", "category", "platform",
}


@dataclass
class AttributeAnalysis:
    total: int
    threshold: float
    all_attrs: dict[str, float] = field(default_factory=dict)
    recommended: list[str] = field(default_factory=list)


def analyze_json(
    json_path: str | Path,
    threshold: float = 0.5,
) -> AttributeAnalysis:
    """
    Count how often each nested attribute key appears across all products.

    threshold: 0.0–1.0. Attributes present in >= (threshold * 100)% of
               products are listed in .recommended.
    """
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = list(data.values())
    if not isinstance(data, list):
        data = []

    total = len(data)
    if total == 0:
        return AttributeAnalysis(total=0, threshold=threshold)

    counts: Counter[str] = Counter()
    for item in data:
        if isinstance(item, dict):
            attrs = item.get("attributes")
            if isinstance(attrs, dict):
                for k in attrs:
                    counts[k] += 1

    all_attrs = {
        k: round(v / total * 100, 1)
        for k, v in sorted(counts.items(), key=lambda x: -x[1])
    }
    recommended = [k for k, pct in all_attrs.items() if pct / 100 >= threshold]

    return AttributeAnalysis(
        total=total,
        threshold=threshold,
        all_attrs=all_attrs,
        recommended=recommended,
    )


def filter_json(
    json_path: str | Path,
    keep_attrs: list[str],
    out_path: str | Path | None = None,
) -> int:
    """
    Rewrite a product JSON keeping only keep_attrs inside each product's attributes dict.
    All MANDATORY_TOP_LEVEL fields are always preserved.
    Returns the number of products written.
    """
    path = Path(json_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = list(data.values())
    if not isinstance(data, list):
        data = []

    keep_set = set(keep_attrs)
    filtered: list[dict] = []

    for item in data:
        if not isinstance(item, dict):
            continue
        new_item = {k: v for k, v in item.items() if k not in ("attributes",)}
        attrs = item.get("attributes", {})
        if isinstance(attrs, dict):
            new_item["attributes"] = {k: v for k, v in attrs.items() if k in keep_set}
        filtered.append(new_item)

    dest = Path(out_path) if out_path else path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(filtered, indent=2, ensure_ascii=False), encoding="utf-8")
    return len(filtered)


def diagnose(json_path: str | Path) -> dict[str, Any]:
    """Quick diagnosis of a product JSON: counts, duplicates, missing mandatory fields."""
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = list(data.values())
    if not isinstance(data, list):
        data = []

    asin_seen: set[str] = set()
    duplicates: list[str] = []
    missing_mandatory: int = 0

    for item in data:
        if not isinstance(item, dict):
            continue
        missing = MANDATORY_TOP_LEVEL - set(item.keys())
        if missing:
            missing_mandatory += 1
        asin = item.get("asin", "")
        if asin in asin_seen:
            duplicates.append(asin)
        else:
            asin_seen.add(asin)

    return {
        "total": len(data),
        "unique_asins": len(asin_seen),
        "duplicates": len(duplicates),
        "missing_mandatory_fields": missing_mandatory,
    }
