#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import standard_ebooks_daemon as catalog_daemon
import standard_ebooks_downloader as downloader

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def tail_jsonl(path: Path, limit: int = 30) -> list[dict]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()[-limit:]
    out = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            out.append({"ts": now_iso(), "type": "info", "message": line})
    return out


class ServiceRuntime:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.output_dir = Path(args.output_dir)
        self.status_file = Path(args.status_file)
        self.events_file = Path(args.events_file)
        self.stop_file = Path(args.stop_file)
        self.job_file = Path(args.job_file)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.current_status = {
            "state": "starting",
            "mode": args.mode,
            "running": True,
            "pid": os.getpid(),
            "started_at": now_iso(),
            "updated_at": now_iso(),
            "output_dir": str(self.output_dir),
            "output_label": args.output_label,
            "total": 0,
            "processed": 0,
            "done": 0,
            "failed": 0,
            "percent": 0,
            "current_item": "",
            "note": "",
            "has_ebook_convert": downloader.has_ebook_convert(),
        }
        write_json(self.job_file, {
            "mode": args.mode,
            "output_dir": str(self.output_dir),
            "output_label": args.output_label,
            "started_at": self.current_status["started_at"],
        })
        self.save()

    def save(self) -> None:
        self.current_status["updated_at"] = now_iso()
        write_json(self.status_file, self.current_status)

    def event(self, level: str, message: str, extra: dict | None = None) -> None:
        payload = {"ts": now_iso(), "type": level, "message": message}
        if extra:
            payload.update(extra)
        append_jsonl(self.events_file, payload)

    def update(self, **kwargs) -> None:
        self.current_status.update(kwargs)
        total = max(0, int(self.current_status.get("total", 0)))
        processed = max(0, int(self.current_status.get("processed", 0)))
        self.current_status["percent"] = round((processed / total) * 100) if total else 0
        self.save()

    def should_stop(self) -> bool:
        return self.stop_file.exists()

    def finish(self, state: str, note: str = "") -> None:
        self.update(state=state, running=False, note=note)
        self.event("system", f"Service finished with state={state}", {"state": state, "note": note})


def sanitize_subfolder(value: str) -> str:
    value = (value or "").strip()
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_", "/") else "-" for ch in value)
    safe = safe.strip("-/") or f"run-{time.strftime('%Y%m%d-%H%M%S')}"
    return safe


def build_downloader_args(args: argparse.Namespace) -> SimpleNamespace:
    return SimpleNamespace(
        delay=args.delay,
        timeout=args.timeout,
        download_advanced_epub=args.download_advanced_epub,
        download_azw3=args.download_azw3,
        download_kepub=args.download_kepub,
        download_xhtml=args.download_xhtml,
        download_zip=args.download_zip,
        extract_zip=args.extract_zip,
        convert_pdf=args.convert_pdf,
    )


def load_urls(path: Path) -> list[str]:
    if not path.exists():
        return []
    lines = [line.strip() for line in path.read_text(encoding="utf-8-sig").splitlines()]
    return [line for line in lines if line]


def run_manual(args: argparse.Namespace, runtime: ServiceRuntime) -> int:
    urls = load_urls(Path(args.urls_file))
    dl_args = build_downloader_args(args)
    runtime.update(total=len(urls), note="Starting manual downloads")
    runtime.event("system", "Manual mode started", {"total": len(urls), "output_label": args.output_label})

    client = downloader.Client(delay=args.delay, timeout=args.timeout)
    manifest = downloader.Manifest(runtime.output_dir / "manifest.json")

    for idx, url in enumerate(urls, start=1):
        if runtime.should_stop():
            runtime.finish("stopped", "Stop flag received")
            return 0

        runtime.update(current_item=url, processed=idx - 1)
        runtime.event("info", f"Processing {url}", {"source_url": url})
        try:
            rec = downloader.process_url(url, runtime.output_dir, client, dl_args, manifest)
            is_done = rec.status == "done"
            runtime.update(
                processed=idx,
                done=int(runtime.current_status["done"]) + (1 if is_done else 0),
                failed=int(runtime.current_status["failed"]) + (0 if is_done else 1),
                current_item=rec.title or rec.source_url,
                note=rec.note.strip(),
            )
            runtime.event(
                "success" if is_done else "warning",
                f"{rec.status.upper()}: {rec.title or rec.source_url}",
                {
                    "source_url": rec.source_url,
                    "title": rec.title,
                    "status": rec.status,
                    "epub_path": rec.epub_path,
                    "pdf_path": rec.pdf_path,
                    "zip_path": rec.zip_path,
                    "note": rec.note.strip(),
                },
            )
        except Exception as exc:
            runtime.update(
                processed=idx,
                failed=int(runtime.current_status["failed"]) + 1,
                current_item=url,
                note=str(exc),
            )
            runtime.event("error", f"ERROR: {url}", {"source_url": url, "note": str(exc)})

    runtime.finish("completed", "Manual run completed")
    return 0


def run_catalog(args: argparse.Namespace, runtime: ServiceRuntime) -> int:
    state_path = runtime.output_dir / "state.json"
    log_note = "Catalog daemon started"
    runtime.update(note=log_note)
    runtime.event("system", log_note, {"output_label": args.output_label})

    daemon_args = SimpleNamespace(
        out_dir=str(runtime.output_dir),
        batch_size=args.batch_size,
        delay=args.delay,
        timeout=args.timeout,
        state_file=str(state_path),
        interval=args.interval,
        loop=False,
        sleep_on_error=30,
        download_advanced_epub=args.download_advanced_epub,
        download_azw3=args.download_azw3,
        download_kepub=args.download_kepub,
        download_xhtml=args.download_xhtml,
        download_zip=args.download_zip,
        extract_zip=args.extract_zip,
        convert_pdf=args.convert_pdf,
    )

    while True:
        if runtime.should_stop():
            runtime.finish("stopped", "Stop flag received")
            return 0

        processed = catalog_daemon.run_batch(daemon_args)
        daemon_state = read_json(state_path, {})
        runtime.update(
            total=int(daemon_state.get("processed_count", 0)) + max(0, int(args.batch_size)),
            processed=int(daemon_state.get("processed_count", 0)),
            done=int(daemon_state.get("done_count", 0)),
            failed=int(daemon_state.get("error_count", 0)),
            current_item=f"Catalog page {daemon_state.get('page', 1)}",
            note=f"Last batch processed={processed}",
        )
        runtime.event(
            "info",
            f"Batch finished. processed={processed}",
            {
                "page": daemon_state.get("page", 1),
                "processed_count": daemon_state.get("processed_count", 0),
                "done_count": daemon_state.get("done_count", 0),
                "error_count": daemon_state.get("error_count", 0),
            },
        )

        if not args.loop:
            runtime.finish("completed", "Catalog batch completed")
            return 0

        for _ in range(max(1, args.interval)):
            if runtime.should_stop():
                runtime.finish("stopped", "Stop flag received")
                return 0
            time.sleep(1)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Standard Ebooks service wrapper")
    ap.add_argument("--mode", choices=["manual", "daemon"], required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--output-label", required=True)
    ap.add_argument("--status-file", required=True)
    ap.add_argument("--events-file", required=True)
    ap.add_argument("--stop-file", required=True)
    ap.add_argument("--job-file", required=True)
    ap.add_argument("--urls-file", default="")
    ap.add_argument("--delay", type=float, default=5.0)
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("--batch-size", type=int, default=25)
    ap.add_argument("--interval", type=int, default=600)
    ap.add_argument("--loop", action="store_true")
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
    runtime = ServiceRuntime(args)

    def handle_signal(signum, frame):
        runtime.event("warning", f"Signal received: {signum}")
        runtime.finish("stopped", f"Signal received: {signum}")
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    try:
        if args.mode == "manual":
            return run_manual(args, runtime)
        return run_catalog(args, runtime)
    except Exception as exc:
        runtime.event("error", "Fatal error", {"note": str(exc)})
        runtime.finish("error", str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
