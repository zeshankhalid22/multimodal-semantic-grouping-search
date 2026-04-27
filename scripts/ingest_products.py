#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.core import database, ml_model  # noqa: E402
from src.core.ingestion import IngestResult, IngestStatus, ingest_from_file  # noqa: E402

_RESET = "\033[0m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_CYAN = "\033[36m"
_BOLD = "\033[1m"


def _colour(text: str, code: str) -> str:
    return f"{code}{text}{_RESET}" if sys.stdout.isatty() else text


_STATUS_SYMBOLS = {
    IngestStatus.INSERTED: (_GREEN, "✓"),
    IngestStatus.SKIPPED_DUPLICATE: (_YELLOW, "~"),
    IngestStatus.SKIPPED_MISSING_IMAGE: (_YELLOW, "!"),
    IngestStatus.SKIPPED_INVALID: (_YELLOW, "!"),
    IngestStatus.FAILED: (_RED, "✗"),
}


def _make_progress_callback(verbose: bool):
    counter = [0]

    def callback(result: IngestResult) -> None:
        counter[0] += 1
        colour, symbol = _STATUS_SYMBOLS.get(result.status, ("", "?"))
        label = _colour(symbol, colour)
        suffix = f"  {result.reason}" if (verbose or result.status != IngestStatus.INSERTED) else ""
        print(f"  {label} [{counter[0]:>5}] {result.asin:<15} {result.status.value}{suffix}")

    return callback


def _print_summary(summary, elapsed: float, dry_run: bool) -> None:
    tag = _colour("[DRY RUN] ", _CYAN) if dry_run else ""
    print()
    print(_colour("─" * 52, _BOLD))
    print(f"{tag}Ingestion complete — {summary.total} records processed  ({elapsed:.1f}s)")
    print(_colour("─" * 52, _BOLD))

    rows = [
        ("inserted",           summary.inserted,              _GREEN),
        ("skipped duplicate",  summary.skipped_duplicate,     _YELLOW),
        ("skipped no image",   summary.skipped_missing_image, _YELLOW),
        ("skipped invalid",    summary.skipped_invalid,       _YELLOW),
        ("failed",             summary.failed,                _RED),
    ]
    for label, count, colour in rows:
        formatted = _colour(str(count), colour) if count else str(count)
        print(f"  {label:<24}: {formatted}")

    if summary.failed:
        print()
        print(_colour("Failed records:", _RED))
        for r in summary.results:
            if r.status == IngestStatus.FAILED:
                print(f"  {r.asin}: {r.reason}")

    print()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ingest_products",
        description="Ingest product JSON into the product_inventory table.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--json-file", required=True, metavar="PATH",
        help="Path to the product JSON file (must be a top-level JSON array).",
    )
    parser.add_argument(
        "--image-root", default="", metavar="DIR",
        help="Base directory for resolving relative image_path values. Overrides IMAGE_ROOT in .env.",
    )
    parser.add_argument(
        "--limit", type=int, default=None, metavar="N",
        help="Stop after N records.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Validate records and check images without writing to DB or loading the ML model.",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Print reason text for every record, not just failures/skips.",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    json_path = Path(args.json_file)
    if not json_path.is_file():
        print(_colour(f"✗ JSON file not found: {json_path}", _RED), file=sys.stderr)
        sys.exit(1)

    print(f"{'[DRY RUN] ' if args.dry_run else ''}Ingesting: {json_path}")

    if not args.dry_run:
        print("  Initialising DB pool …", end=" ", flush=True)
        database.init_pool()
        print("done")

        print("  Loading ML model …", end=" ", flush=True)
        ml_model.load_model()
        print("done")
    else:
        print("  [DRY RUN] Skipping DB / model initialisation.")

    if args.limit:
        print(f"  Limit: {args.limit} records")
    print()

    callback = _make_progress_callback(verbose=args.verbose)
    start = time.monotonic()

    try:
        summary = ingest_from_file(
            json_path=json_path,
            image_root=args.image_root,
            dry_run=args.dry_run,
            limit=args.limit,
            progress_callback=callback,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(_colour(f"\n✗ {exc}", _RED), file=sys.stderr)
        sys.exit(1)
    finally:
        if not args.dry_run:
            database.close_pool()

    elapsed = time.monotonic() - start
    _print_summary(summary, elapsed, dry_run=args.dry_run)

    if summary.failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
