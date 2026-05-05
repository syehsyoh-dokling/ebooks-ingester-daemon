#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


PATH_FIELDS = (
    "cover_path",
    "epub_path",
    "azw3_path",
    "kepub_path",
    "xhtml_path",
    "advanced_epub_path",
    "zip_path",
    "pdf_path",
)


def split_any_path(value: str) -> list[str]:
    return [part for part in re.split(r"[\\/]+", value or "") if part]


def remap_path(root_dir: Path, value: str) -> str:
    parts = split_any_path(value)
    if len(parts) < 2:
        return value
    folder_name = parts[-2]
    file_name = parts[-1]
    candidate = root_dir / folder_name / file_name
    return str(candidate) if candidate.exists() else value


def main() -> int:
    ap = argparse.ArgumentParser(description="Migrate Standard Ebooks seed manifest paths to a new root")
    ap.add_argument("--root-dir", required=True)
    args = ap.parse_args()

    root_dir = Path(args.root_dir)
    manifest_path = root_dir / "manifest.json"
    state_path = root_dir / "state.json"

    if not manifest_path.exists():
        raise SystemExit(f"manifest not found: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    items = manifest.get("items", [])

    seen_urls: set[str] = set()
    for item in items:
        for field_name in PATH_FIELDS:
            raw = item.get(field_name) or ""
            if raw:
                item[field_name] = remap_path(root_dir, raw)
        pdf_path = item.get("pdf_path") or ""
        if pdf_path and Path(pdf_path).exists():
            seen_urls.add(item.get("source_url", ""))

    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8-sig"))
    else:
        state = {}

    current_seen = set(state.get("seen_urls", []))
    state["seen_urls"] = sorted(url for url in current_seen.union(seen_urls) if url)
    state["done_count"] = max(int(state.get("done_count", 0) or 0), len(state["seen_urls"]))
    state.setdefault("page", 1)
    state.setdefault("processed_count", 0)
    state.setdefault("error_count", 0)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "root_dir": str(root_dir),
        "items": len(items),
        "seen_urls": len(state["seen_urls"]),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
