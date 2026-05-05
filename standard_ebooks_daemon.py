#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path

import standard_ebooks_downloader as downloader

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def load_state(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            pass
    return {
        "page": 1,
        "seen_urls": [],
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": "",
        "processed_count": 0,
        "done_count": 0,
        "error_count": 0,
    }


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def needs_completion(rec: downloader.ItemRecord | None, args: argparse.Namespace) -> bool:
    if rec is None:
        return True
    if not rec.cover_path:
        return True
    if not rec.epub_path:
        return True
    if args.convert_pdf and not rec.pdf_path:
        return True
    if args.download_advanced_epub and not rec.advanced_epub_path:
        return True
    if args.download_azw3 and not rec.azw3_path:
        return True
    if args.download_kepub and not rec.kepub_path:
        return True
    if args.download_xhtml and not rec.xhtml_path:
        return True
    if args.download_zip and not rec.zip_path:
        return True
    return False


def catalog_url(page: int) -> str:
    if page <= 1:
        return "https://standardebooks.org/ebooks"
    return f"https://standardebooks.org/ebooks?page={page}"


def collect_book_urls(client: downloader.Client, page: int) -> list[str]:
    html = client.get(catalog_url(page)).decode("utf-8", errors="ignore")
    urls: list[str] = []
    seen: set[str] = set()
    for href in re.findall(r'href="([^"]+)"', html, flags=re.I):
        full = downloader.normalize_url(href)
        parsed = urllib.parse.urlparse(full)
        path = parsed.path.rstrip("/")
        if not path.startswith("/ebooks/"):
            continue
        if path == "/ebooks" or path.endswith("/downloads"):
            continue
        if "?" in href or "#" in href:
            continue
        parts = [p for p in path.split("/") if p]
        if len(parts) < 3:
            continue
        normalized = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))
        if normalized not in seen:
            urls.append(normalized)
            seen.add(normalized)
    return urls


def run_batch(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = out_dir / "logs"
    state_path = Path(args.state_file)
    if not state_path.is_absolute():
        state_path = out_dir / state_path

    state = load_state(state_path)
    seen_urls = set(state.get("seen_urls", []))
    client = downloader.Client(delay=args.delay, timeout=args.timeout)
    manifest = downloader.Manifest(out_dir / "manifest.json")

    processed = 0
    page = max(1, int(state.get("page", 1)))
    while processed < args.batch_size:
        urls = collect_book_urls(client, page)
        if not urls:
            page = 1
            state["page"] = page
            save_state(state_path, state)
            break

        for url in urls:
            if processed >= args.batch_size:
                break
            existing = manifest.get(url)
            if url in seen_urls and not needs_completion(existing, args):
                continue

            rec = None
            try:
                rec = downloader.process_url(url, out_dir, client, args, manifest)
                payload = {
                    "source_url": rec.source_url,
                    "title": rec.title,
                    "status": rec.status,
                    "epub_path": rec.epub_path,
                    "pdf_path": rec.pdf_path,
                    "note": rec.note.strip(),
                }
                print(json.dumps(payload, ensure_ascii=True), flush=True)
                append_jsonl(logs_dir / "run.jsonl", payload)
                if rec.status == "done":
                    state["done_count"] = int(state.get("done_count", 0)) + 1
                    append_jsonl(logs_dir / "success.jsonl", payload)
                else:
                    append_jsonl(logs_dir / "partial.jsonl", payload)
                    if "429" in payload.get("note", ""):
                        print("Rate limited by Standard Ebooks. Pausing this batch.", flush=True)
                        save_state(state_path, state)
                        return processed
            except Exception as exc:
                payload = {"source_url": url, "status": "error", "note": str(exc)}
                print(json.dumps(payload, ensure_ascii=True), flush=True)
                state["error_count"] = int(state.get("error_count", 0)) + 1
                append_jsonl(logs_dir / "error.jsonl", payload)
                if "429" in str(exc):
                    print("Rate limited by Standard Ebooks. Pausing this batch.", flush=True)
                    save_state(state_path, state)
                    return processed

            if rec and rec.pdf_path:
                seen_urls.add(url)
                state["seen_urls"] = sorted(seen_urls)
            state["processed_count"] = int(state.get("processed_count", 0)) + 1
            processed += 1
            save_state(state_path, state)

        page += 1
        state["page"] = page
        save_state(state_path, state)

    print(f"Finished batch. processed={processed} page={state.get('page')} output={out_dir}", flush=True)
    return processed


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Standard Ebooks catalog daemon")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--batch-size", type=int, default=100)
    ap.add_argument("--interval", type=int, default=600)
    ap.add_argument("--delay", type=float, default=2.0)
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("--state-file", default="state.json")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--sleep-on-error", type=int, default=60)
    ap.add_argument("--download-advanced-epub", action="store_true")
    ap.add_argument("--download-azw3", action="store_true")
    ap.add_argument("--download-kepub", action="store_true")
    ap.add_argument("--download-xhtml", action="store_true")
    ap.add_argument("--download-zip", action="store_true")
    ap.add_argument("--extract-zip", action="store_true")
    ap.add_argument("--convert-pdf", action="store_true")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    while True:
        try:
            run_batch(args)
        except KeyboardInterrupt:
            return 130
        except Exception as exc:
            print(f"Loop error: {exc}", flush=True)
            time.sleep(max(1, args.sleep_on_error))

        if not args.loop:
            return 0
        print(f"Sleeping {args.interval} seconds before next batch...", flush=True)
        time.sleep(max(1, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
