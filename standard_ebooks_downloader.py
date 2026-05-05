#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, asdict
from pathlib import Path
from tempfile import TemporaryDirectory

try:
    from ebooklib import epub, ITEM_DOCUMENT
except Exception:
    epub = None
    ITEM_DOCUMENT = None

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None

try:
    from weasyprint import HTML
except Exception:
    HTML = None

USER_AGENT = "Saifuddin-StandardEbooks-Downloader/2.0 (+personal-use; throttled)"
EBOOK_CONVERT_CANDIDATES = (
    "/opt/calibre/ebook-convert",
    "/opt/calibre-official/ebook-convert",
    "/usr/bin/ebook-convert",
)


@dataclass
class ItemRecord:
    source_url: str
    item_type: str = ""
    title: str = ""
    author: str = ""
    cover_url: str = ""
    cover_path: str = ""
    epub_url: str = ""
    azw3_url: str = ""
    kepub_url: str = ""
    xhtml_url: str = ""
    advanced_epub_url: str = ""
    zip_url: str = ""
    epub_path: str = ""
    azw3_path: str = ""
    kepub_path: str = ""
    xhtml_path: str = ""
    advanced_epub_path: str = ""
    zip_path: str = ""
    pdf_path: str = ""
    pdf_mode: str = ""
    status: str = "pending"
    note: str = ""


class Client:
    def __init__(self, delay: float = 2.0, timeout: int = 60) -> None:
        self.delay = delay
        self.timeout = timeout
        self._last = 0.0

    def _wait(self) -> None:
        elapsed = time.time() - self._last
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)

    def get(self, url: str) -> bytes:
        self._wait()
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read()
        finally:
            self._last = time.time()

    def download(self, url: str, dest: Path) -> None:
        data = self.get(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)


class Manifest:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.records: list[ItemRecord] = []
        if path.exists():
            try:
                obj = json.loads(path.read_text(encoding="utf-8"))
                for item in obj.get("items", []):
                    self.records.append(ItemRecord(**item))
            except Exception:
                pass

    def get(self, source_url: str) -> ItemRecord | None:
        for record in self.records:
            if record.source_url == source_url:
                return record
        return None

    def save(self) -> None:
        payload = {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "items": [asdict(v) for v in self.records],
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def add(self, rec: ItemRecord) -> None:
        self.records = [item for item in self.records if item.source_url != rec.source_url]
        self.records.append(rec)
        self.save()


def sanitize_filename(text: str, limit: int = 140) -> str:
    text = re.sub(r'[\\/:*?"<>|]+', "_", text).strip()
    text = re.sub(r"\s+", " ", text)
    return (text[:limit] or "untitled").rstrip(" .")


def nonempty_file(path: Path) -> bool:
    try:
        return path.exists() and path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def split_any_path(value: str) -> list[str]:
    return [part for part in re.split(r"[\\/]+", value or "") if part]


def path_parent_folder_name(value: str) -> str:
    parts = split_any_path(value)
    if len(parts) >= 2:
        return parts[-2]
    return ""


def first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if nonempty_file(path):
            return path
    return None


def normalize_url(url: str) -> str:
    return urllib.parse.urljoin("https://standardebooks.org/", url)


def direct_download_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    if params.get("source") == ["download"]:
        return url
    query = f"{parsed.query}&source=download" if parsed.query else "source=download"
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, query, parsed.fragment))


def slurp_text(client: Client, url: str) -> str:
    return client.get(url).decode("utf-8", errors="ignore")


def find_title(html_text: str) -> str:
    m = re.search(r"<title>(.*?)</title>", html_text, flags=re.I | re.S)
    if m:
        t = html.unescape(re.sub(r"\s+", " ", m.group(1))).strip()
        t = re.sub(r"\s+\|\s+Standard Ebooks.*$", "", t)
        t = re.sub(r"\s+-\s+Free ebook download\s+-\s+Standard Ebooks.*$", "", t)
        return t
    m = re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', html_text, flags=re.I)
    return html.unescape(m.group(1)).strip() if m else ""


def find_author(html_text: str) -> str:
    patterns = [
        r'<meta\s+name="author"\s+content="([^"]+)"',
        r'<meta\s+property="book:author"\s+content="([^"]+)"',
        r'<a[^>]+rel="author"[^>]*>(.*?)</a>',
    ]
    for pat in patterns:
        m = re.search(pat, html_text, flags=re.I | re.S)
        if m:
            return html.unescape(re.sub(r"<[^>]+>", " ", m.group(1))).strip()
    return ""


def find_cover(html_text: str) -> str:
    meta = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]*>', html_text, flags=re.I)
    if meta:
        content = re.search(r'content=["\']([^"\']+)["\']', meta.group(0), flags=re.I)
        if content:
            return normalize_url(content.group(1))
    meta = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\'][^>]*>', html_text, flags=re.I)
    if meta:
        return normalize_url(meta.group(1))
    img = re.search(r'<img[^>]+class=["\'][^"\']*cover[^"\']*["\'][^>]+src=["\']([^"\']+)["\']', html_text, flags=re.I)
    if img:
        return normalize_url(img.group(1))
    return ""


def infer_download_page(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.rstrip("/")
    if path.endswith("/downloads"):
        return url
    if "/ebooks/" in path:
        return urllib.parse.urlunparse(
            (parsed.scheme or "https", parsed.netloc or "standardebooks.org", path + "/downloads", "", "", "")
        )
    return url


def collect_links(html_text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    hrefs = re.findall(r'href="([^"]+)"', html_text, flags=re.I)

    for href in hrefs:
        full = normalize_url(href)
        low = full.lower()
        if "/downloads/" not in low:
            continue
        if low.endswith(".epub") and "advanced" not in low and "kepub" not in low:
            found.setdefault("epub_url", direct_download_url(full))
        elif low.endswith(".azw3"):
            found.setdefault("azw3_url", direct_download_url(full))
        elif "kepub" in low and low.endswith(".epub"):
            found.setdefault("kepub_url", direct_download_url(full))
        elif low.endswith(".xhtml") or low.endswith(".html"):
            found.setdefault("xhtml_url", direct_download_url(full))
        elif "advanced" in low and low.endswith(".epub"):
            found.setdefault("advanced_epub_url", direct_download_url(full))
        elif low.endswith(".zip"):
            found.setdefault("zip_url", direct_download_url(full))

    if "zip_url" not in found:
        m = re.search(r'https://standardebooks\.org/[^"\']+/downloads', html_text, flags=re.I)
        if m:
            page_url = m.group(0).rstrip("/")
            found["zip_url"] = direct_download_url(page_url + "/epub.zip")

    return found


def choose_folder_name(rec: ItemRecord) -> str:
    base = rec.title or Path(urllib.parse.urlparse(rec.source_url).path).name or "standard-ebooks-item"
    if rec.author:
        base = f"{rec.author} - {base}"
    path_parts = [p for p in urllib.parse.urlparse(rec.source_url).path.split("/") if p]
    slug = path_parts[-1] if path_parts else ""
    if len(path_parts) > 2 and slug in {"various-translators"}:
        slug = path_parts[-2]
    prefix = sanitize_filename(slug.replace("-", " "), limit=50)
    return sanitize_filename(f"{prefix} - {base}", limit=96)


def resolve_item_dir(out_dir: Path, rec: ItemRecord, manifest: Manifest) -> Path:
    existing = manifest.get(rec.source_url)
    candidate_names: list[str] = []

    if existing:
        for raw in [
            existing.pdf_path,
            existing.epub_path,
            existing.advanced_epub_path,
            existing.azw3_path,
            existing.kepub_path,
            existing.xhtml_path,
            existing.zip_path,
            existing.cover_path,
        ]:
            folder_name = path_parent_folder_name(raw)
            if folder_name:
                candidate_names.append(folder_name)

    for folder_name in candidate_names:
        candidate = out_dir / folder_name
        if candidate.exists():
            return candidate

    return out_dir / choose_folder_name(rec)


def set_existing_paths(rec: ItemRecord, item_dir: Path) -> None:
    cover = first_existing(list(item_dir.glob("cover.*")))
    if cover and not rec.cover_path:
        rec.cover_path = str(cover)

    epub = first_existing([path for path in item_dir.glob("*.epub") if "advanced" not in path.name and "kepub" not in path.name])
    if epub and not rec.epub_path:
        rec.epub_path = str(epub)

    advanced_epub = first_existing(list(item_dir.glob("*advanced*.epub")))
    if advanced_epub and not rec.advanced_epub_path:
        rec.advanced_epub_path = str(advanced_epub)

    azw3 = first_existing(list(item_dir.glob("*.azw3")))
    if azw3 and not rec.azw3_path:
        rec.azw3_path = str(azw3)

    kepub = first_existing([path for path in item_dir.glob("*.epub") if "kepub" in path.name.lower()])
    if kepub and not rec.kepub_path:
        rec.kepub_path = str(kepub)

    xhtml = first_existing(list(item_dir.glob("*.xhtml")) + list(item_dir.glob("*.html")))
    if xhtml and not rec.xhtml_path:
        rec.xhtml_path = str(xhtml)

    zip_file = first_existing(list(item_dir.glob("*.zip")))
    if zip_file and not rec.zip_path:
        rec.zip_path = str(zip_file)

    pdf = first_existing([item_dir / "book.pdf"] + list(item_dir.glob("*.pdf")))
    if pdf and not rec.pdf_path:
        rec.pdf_path = str(pdf)
        if not rec.pdf_mode:
            rec.pdf_mode = "existing"


def copy_existing_record_data(rec: ItemRecord, existing: ItemRecord | None) -> None:
    if not existing:
        return
    for field_name in (
        "title",
        "author",
        "cover_url",
        "epub_url",
        "azw3_url",
        "kepub_url",
        "xhtml_url",
        "advanced_epub_url",
        "zip_url",
        "cover_path",
        "epub_path",
        "azw3_path",
        "kepub_path",
        "xhtml_path",
        "advanced_epub_path",
        "zip_path",
        "pdf_path",
        "pdf_mode",
    ):
        if not getattr(rec, field_name):
            setattr(rec, field_name, getattr(existing, field_name))


def asset_required_and_missing(rec: ItemRecord, args: argparse.Namespace) -> list[str]:
    missing: list[str] = []
    if not rec.cover_path:
        missing.append("cover")
    if not rec.epub_path:
        missing.append("epub")
    if args.download_advanced_epub and not rec.advanced_epub_path:
        missing.append("advanced_epub")
    if args.download_azw3 and not rec.azw3_path:
        missing.append("azw3")
    if args.download_kepub and not rec.kepub_path:
        missing.append("kepub")
    if args.download_xhtml and not rec.xhtml_path:
        missing.append("xhtml")
    if args.download_zip and not rec.zip_path:
        missing.append("zip")
    if args.convert_pdf and not rec.pdf_path:
        missing.append("pdf")
    return missing


def download_if(url: str, client: Client, path: Path) -> str:
    if not url:
        return ""
    try:
        client.download(url, path)
        return str(path)
    except Exception as e:
        return f"ERROR:{e}"


def has_ebook_convert() -> bool:
    return find_ebook_convert() is not None or has_weasyprint_pdf_fallback()


def find_ebook_convert() -> str | None:
    for candidate in EBOOK_CONVERT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return shutil.which("ebook-convert")


def has_weasyprint_pdf_fallback() -> bool:
    return epub is not None and ITEM_DOCUMENT is not None and BeautifulSoup is not None and HTML is not None


def locate_extracted_doc(tmp_path: Path, rel_path: str) -> Path | None:
    rel = Path(rel_path)
    candidates: list[Path] = [
        tmp_path / rel,
        tmp_path / "epub" / rel,
        tmp_path / rel.name,
    ]

    parent_parts = rel.parts[:-1]
    if parent_parts:
        candidates.append(tmp_path.joinpath(*parent_parts, rel.name))
        candidates.append(tmp_path / "epub" / Path(*parent_parts) / rel.name)

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate

    matches = list(tmp_path.rglob(rel.name))
    return matches[0] if matches else None


def convert_epub_to_pdf_weasyprint(epub_path: Path, pdf_path: Path) -> tuple[bool, str]:
    if not has_weasyprint_pdf_fallback():
        return False, "WeasyPrint fallback is not available"

    try:
        book = epub.read_epub(str(epub_path))
        spine_ids = [item_id for item_id, _ in getattr(book, "spine", []) if item_id != "nav"]
        spine_docs: list[str] = []
        for item_id in spine_ids:
            item = book.get_item_with_id(item_id)
            if item is not None and item.get_type() == ITEM_DOCUMENT:
                spine_docs.append(item.file_name)

        with TemporaryDirectory(prefix="se-epub-") as tmp_dir:
            tmp_path = Path(tmp_dir)
            with zipfile.ZipFile(epub_path, "r") as zf:
                zf.extractall(tmp_path)

            rendered_sections: list[str] = []
            if spine_docs:
                ordered_docs = []
                for rel_path in spine_docs:
                    located = locate_extracted_doc(tmp_path, rel_path)
                    if located:
                        ordered_docs.append(located)
            else:
                ordered_docs = sorted(list(tmp_path.rglob("*.xhtml")) + list(tmp_path.rglob("*.html")))

            for doc_path in ordered_docs:
                try:
                    raw_html = doc_path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                soup = BeautifulSoup(raw_html, "html.parser")
                body = soup.body or soup
                rendered_sections.append(f'<section class="chapter">{body.decode_contents()}</section>')

            if not rendered_sections:
                return False, "No XHTML/HTML spine documents found in EPUB"

            title_meta = book.get_metadata("DC", "title")
            title_text = title_meta[0][0] if title_meta else epub_path.stem
            html_text = f"""
            <html>
              <head>
                <meta charset="utf-8">
                <title>{html.escape(title_text)}</title>
                <style>
                  @page {{ size: A4; margin: 18mm 16mm; }}
                  body {{ font-family: serif; font-size: 11pt; line-height: 1.5; color: #111; }}
                  h1, h2, h3, h4 {{ break-after: avoid; }}
                  p {{ margin: 0 0 0.9em; }}
                  section.chapter {{ break-before: page; }}
                  section.chapter:first-child {{ break-before: auto; }}
                  img, svg {{ max-width: 100%; height: auto; }}
                  blockquote {{ margin: 0 0 1em 1.5em; }}
                  pre {{ white-space: pre-wrap; }}
                </style>
              </head>
              <body>
                {''.join(rendered_sections)}
              </body>
            </html>
            """
            HTML(string=html_text, base_url=str(tmp_path)).write_pdf(str(pdf_path))
        return True, ""
    except Exception as exc:
        return False, str(exc)


def convert_epub_to_pdf(epub_path: Path, pdf_path: Path) -> tuple[bool, str]:
    exe = find_ebook_convert()
    if not exe:
        return False, "ebook-convert not found in PATH"
    runtime_dir = Path(f"/tmp/runtime-calibre-{os.getuid()}")
    home_dir = Path(f"/tmp/calibre-home-{os.getuid()}")
    runtime_dir.mkdir(parents=True, exist_ok=True)
    home_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(runtime_dir, 0o700)
    env = os.environ.copy()
    env["XDG_RUNTIME_DIR"] = str(runtime_dir)
    env["HOME"] = str(home_dir)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QTWEBENGINE_DISABLE_SANDBOX"] = "1"
    try:
        subprocess.run(
            [exe, str(epub_path), str(pdf_path)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        return True, ""
    except subprocess.CalledProcessError as e:
        msg = (e.stderr or e.stdout or str(e)).strip()
        fallback_ok, fallback_msg = convert_epub_to_pdf_weasyprint(epub_path, pdf_path)
        if fallback_ok:
            return True, ""
        return False, f"{msg}; fallback_failed:{fallback_msg}"
    except Exception as exc:
        fallback_ok, fallback_msg = convert_epub_to_pdf_weasyprint(epub_path, pdf_path)
        if fallback_ok:
            return True, ""
        return False, f"{exc}; fallback_failed:{fallback_msg}"


def maybe_extract_zip(zip_path: Path, extract_dir: Path) -> None:
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)


def find_all_epubs_in_dir(folder: Path) -> list[Path]:
    return sorted(folder.rglob("*.epub"))


def convert_all_epubs(folder: Path) -> tuple[int, list[str]]:
    converted = 0
    errors: list[str] = []
    for epub in find_all_epubs_in_dir(folder):
        pdf_path = epub.with_suffix(".pdf")
        ok, msg = convert_epub_to_pdf(epub, pdf_path)
        if ok:
            converted += 1
        else:
            errors.append(f"{epub.name}: {msg}")
    return converted, errors


def process_url(url: str, out_dir: Path, client: Client, args: argparse.Namespace, manifest: Manifest) -> ItemRecord:
    rec = ItemRecord(source_url=url)
    existing_record = manifest.get(url)
    copy_existing_record_data(rec, existing_record)
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.rstrip("/")

    if path.endswith(".zip"):
        rec.item_type = "bulk_zip"
        rec.zip_url = url
        rec.title = Path(path).name

        item_dir = out_dir / choose_folder_name(rec)
        item_dir.mkdir(parents=True, exist_ok=True)

        zip_path = item_dir / Path(path).name
        res = download_if(rec.zip_url, client, zip_path)
        if res.startswith("ERROR:"):
            rec.status = "error"
            rec.note = res
            manifest.add(rec)
            return rec

        rec.zip_path = str(zip_path)

        if args.extract_zip:
            try:
                extract_dir = item_dir / "extracted"
                maybe_extract_zip(zip_path, extract_dir)
                rec.status = "done"
                rec.note = "zip_downloaded_and_extracted"

                if args.convert_pdf:
                    converted, errors = convert_all_epubs(extract_dir)
                    if converted:
                        rec.pdf_mode = "converted_from_epub"
                        rec.pdf_path = str(extract_dir)
                        rec.note += f"; pdf_converted:{converted}"
                    if errors:
                        rec.note += "; " + " | ".join(errors[:10])
            except Exception as e:
                rec.status = "partial"
                rec.note = f"zip_downloaded_but_extract_failed: {e}"
                manifest.add(rec)
                return rec
        else:
            rec.status = "done"
            rec.note = "zip_downloaded"

        manifest.add(rec)
        return rec

    if not path.endswith("/downloads") and "/ebooks/" in path:
        page_html = slurp_text(client, url)
        rec.item_type = "ebook_page"
    else:
        page_html = slurp_text(client, url)
        rec.item_type = "download_page"

    rec.title = find_title(page_html) or rec.title
    rec.author = find_author(page_html) or rec.author
    rec.cover_url = find_cover(page_html) or rec.cover_url

    links = collect_links(page_html)
    for k, v in links.items():
        if not getattr(rec, k):
            setattr(rec, k, v)

    item_dir = resolve_item_dir(out_dir, rec, manifest)
    item_dir.mkdir(parents=True, exist_ok=True)
    (item_dir / "page.html").write_text(page_html, encoding="utf-8")
    set_existing_paths(rec, item_dir)

    if rec.cover_url and not rec.cover_path:
        cover_ext = Path(urllib.parse.urlparse(rec.cover_url).path).suffix or ".jpg"
        cover_path = item_dir / f"cover{cover_ext}"
        res = download_if(rec.cover_url, client, cover_path)
        if not res.startswith("ERROR:"):
            rec.cover_path = res
        else:
            rec.note += f" {res}"

    if rec.epub_url and not rec.epub_path:
        res = download_if(rec.epub_url, client, item_dir / Path(urllib.parse.urlparse(rec.epub_url).path).name)
        if not res.startswith("ERROR:"):
            rec.epub_path = res
        else:
            rec.note += f" epub_download_failed:{res};"

    if args.download_advanced_epub and rec.advanced_epub_url and not rec.advanced_epub_path:
        res = download_if(rec.advanced_epub_url, client, item_dir / Path(urllib.parse.urlparse(rec.advanced_epub_url).path).name)
        if not res.startswith("ERROR:"):
            rec.advanced_epub_path = res
        else:
            rec.note += f" advanced_epub_download_failed:{res};"

    if args.download_azw3 and rec.azw3_url and not rec.azw3_path:
        res = download_if(rec.azw3_url, client, item_dir / Path(urllib.parse.urlparse(rec.azw3_url).path).name)
        if not res.startswith("ERROR:"):
            rec.azw3_path = res
        else:
            rec.note += f" azw3_download_failed:{res};"

    if args.download_kepub and rec.kepub_url and not rec.kepub_path:
        res = download_if(rec.kepub_url, client, item_dir / Path(urllib.parse.urlparse(rec.kepub_url).path).name)
        if not res.startswith("ERROR:"):
            rec.kepub_path = res
        else:
            rec.note += f" kepub_download_failed:{res};"

    if args.download_xhtml and rec.xhtml_url and not rec.xhtml_path:
        res = download_if(rec.xhtml_url, client, item_dir / Path(urllib.parse.urlparse(rec.xhtml_url).path).name)
        if not res.startswith("ERROR:"):
            rec.xhtml_path = res
        else:
            rec.note += f" xhtml_download_failed:{res};"

    if args.download_zip and rec.zip_url and not rec.zip_path:
        res = download_if(rec.zip_url, client, item_dir / Path(urllib.parse.urlparse(rec.zip_url).path).name)
        if not res.startswith("ERROR:"):
            rec.zip_path = res
            if args.extract_zip:
                try:
                    maybe_extract_zip(Path(rec.zip_path), item_dir / "extracted")
                    if args.convert_pdf:
                        converted, errors = convert_all_epubs(item_dir / "extracted")
                        if converted:
                            rec.note += f" zip_pdf_converted:{converted};"
                        if errors:
                            rec.note += " " + " | ".join(errors[:10])
                except Exception as e:
                    rec.note += f" zip_extract_failed:{e};"

    epub_for_pdf = Path(rec.epub_path) if rec.epub_path else (Path(rec.advanced_epub_path) if rec.advanced_epub_path else None)
    if args.convert_pdf and not rec.pdf_path and epub_for_pdf:
        pdf_path = item_dir / "book.pdf"
        ok, msg = convert_epub_to_pdf(epub_for_pdf, pdf_path)
        if ok:
            rec.pdf_path = str(pdf_path)
            rec.pdf_mode = "converted_from_epub"
        else:
            rec.note += f" pdf_convert_failed:{msg};"

    set_existing_paths(rec, item_dir)
    downloaded_any = any([rec.cover_path, rec.epub_path, rec.advanced_epub_path, rec.azw3_path, rec.kepub_path, rec.xhtml_path, rec.zip_path, rec.pdf_path])
    missing_required = asset_required_and_missing(rec, args)
    if missing_required:
        rec.status = "partial" if downloaded_any else "error"
        rec.note += f" missing_required:{','.join(missing_required)};"
    else:
        rec.status = "done" if downloaded_any else "partial"
    if not downloaded_any and not rec.note:
        rec.note = "No downloadable assets detected on page."

    (item_dir / "metadata.json").write_text(json.dumps(asdict(rec), ensure_ascii=False, indent=2), encoding="utf-8")
    manifest.add(rec)
    return rec


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Standard Ebooks downloader with optional EPUB->PDF conversion")
    ap.add_argument("--out-dir", required=True, help="Output folder")
    ap.add_argument("--urls", nargs="+", required=True, help="One or more Standard Ebooks ebook/download/zip URLs")
    ap.add_argument("--delay", type=float, default=2.0)
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("--download-advanced-epub", action="store_true")
    ap.add_argument("--download-azw3", action="store_true")
    ap.add_argument("--download-kepub", action="store_true")
    ap.add_argument("--download-xhtml", action="store_true")
    ap.add_argument("--download-zip", action="store_true")
    ap.add_argument("--extract-zip", action="store_true")
    ap.add_argument("--convert-pdf", action="store_true", help="Convert EPUB to PDF using Calibre ebook-convert")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    client = Client(delay=args.delay, timeout=args.timeout)
    manifest = Manifest(out_dir / "manifest.json")

    print(json.dumps({
        "tool": "standard_ebooks_downloader",
        "has_ebook_convert": has_ebook_convert(),
        "out_dir": str(out_dir),
    }, ensure_ascii=False))

    ok = 0
    for url in args.urls:
        try:
            rec = process_url(url, out_dir, client, args, manifest)
            payload = {
                "source_url": rec.source_url,
                "item_type": rec.item_type,
                "title": rec.title,
                "author": rec.author,
                "status": rec.status,
                "epub_path": rec.epub_path,
                "zip_path": rec.zip_path,
                "pdf_path": rec.pdf_path,
                "note": rec.note.strip(),
            }
            print(json.dumps(payload, ensure_ascii=False))
            if rec.status == "done":
                ok += 1
        except KeyboardInterrupt:
            raise
        except Exception as e:
            print(json.dumps({"source_url": url, "status": "error", "note": str(e)}, ensure_ascii=False))

    print(f"Finished. {ok}/{len(args.urls)} items completed. Output: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
