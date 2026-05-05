# Standard Ebooks Downloader

Tool ini untuk **Standard Ebooks** dan mendukung:
1. halaman ebook
2. halaman downloads
3. bulk ZIP

## Fitur
- download cover
- download EPUB
- opsi download AZW3 / KEPUB / XHTML
- opsi download bulk ZIP
- opsi extract ZIP
- opsi convert EPUB ke PDF lokal jika `ebook-convert` (Calibre) tersedia
- jika ZIP diextract, semua file EPUB di dalamnya bisa dikonversi ke PDF

## File output
- `page.html`
- `cover.*`
- `metadata.json`
- file ebook yang berhasil diunduh
- `book.pdf` jika conversion sukses
- `manifest.json` di root output

## Contoh 1 — satu ebook
```powershell
py .\standard_ebooks_downloader.py --out-dir "C:\Users\Saifuddin\Documents\StandardEbooks" --urls "https://standardebooks.org/ebooks/emily-bronte/wuthering-heights" --convert-pdf
```

## Contoh 2 — satu download page + bulk zip
```powershell
py .\standard_ebooks_downloader.py --out-dir "C:\Users\Saifuddin\Documents\StandardEbooks" --urls "https://standardebooks.org/ebooks/emily-bronte/wuthering-heights/downloads" --download-zip --extract-zip --convert-pdf
```

## Contoh 3 — bulk ZIP langsung
```powershell
py .\standard_ebooks_downloader.py --out-dir "C:\Users\Saifuddin\Documents\StandardEbooks" --urls "https://standardebooks.org/ebooks/a-a-milne/downloads/epub.zip" --extract-zip --convert-pdf
```

## Catatan penting
Standard Ebooks biasanya menyediakan EPUB/AZW3/KEPUB/XHTML, bukan PDF asli. Jadi untuk PDF, tool ini mengandalkan:
- unduh EPUB asli
- konversi ke PDF lokal dengan `ebook-convert`

## Install Calibre di Windows
Setelah Calibre terpasang, pastikan `ebook-convert` bisa dipanggil dari PowerShell:
```powershell
ebook-convert --version
```
