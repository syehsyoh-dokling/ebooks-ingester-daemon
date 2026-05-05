@echo off
cd /d %~dp0
py standard_ebooks_downloader.py --out-dir "C:\Users\Saifuddin\Documents\StandardEbooks_PDFs" --urls ^
"https://standardebooks.org/ebooks/anne-parrish/the-perennial-bachelor" ^
"https://standardebooks.org/ebooks/jane-austen/pride-and-prejudice" ^
"https://standardebooks.org/ebooks/oscar-wilde/the-picture-of-dorian-gray" ^
--convert-pdf
pause
