# Ebooks Ingester Daemon

Python downloader and ingestion daemon for ebook sources such as Project Gutenberg, Noor Book, and Standard Ebooks.

## Capabilities

- Plugin-based ebook source ingestion.
- Batch download workflows.
- Daemon loop for repeated ingestion.
- Queue client integration.
- Standard Ebooks migration helper.
- Calibre install helper for local ebook workflows.

## Structure

```text
core/
  daemon.py
  queue_client.py
plugins/
  base_plugin.py
  gutenberg.py
  noor_book.py
  standard_ebooks.py
standard_ebooks_daemon.py
standard_ebooks_downloader.py
standard_ebooks_service.py
migrate_standard_ebooks_seed.py
install-calibre.ps1
```

## Run Helpers

Windows batch helpers are included:

```text
run_standard_ebooks_daemon.bat
run_standard_ebooks_downloader.bat
run_standard_ebooks_downloader_multi.bat
```

## Typical Usage

```bash
python standard_ebooks_downloader.py
python standard_ebooks_daemon.py
python standard_ebooks_service.py
```

## Notes

Runtime outputs, downloads, logs, `hasil/`, virtual environments, and Python caches are ignored. This repo should contain source and orchestration scripts only, not downloaded book collections.
