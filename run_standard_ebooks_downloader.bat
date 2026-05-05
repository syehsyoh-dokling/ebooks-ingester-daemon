@echo off
cd /d %~dp0
py standard_ebooks_downloader.py --out-dir "C:\Users\Saifuddin\Documents\StandardEbooks_PDFs" --urls "https://standardebooks.org/ebooks/jane-austen/pride-and-prejudice" --convert-pdf
pause
