@echo off
cd /d %~dp0
if not exist "C:\Users\Saifuddin\Documents\StandardEbooks_PDFs\logs" mkdir "C:\Users\Saifuddin\Documents\StandardEbooks_PDFs\logs"
py standard_ebooks_daemon.py --out-dir "C:\Users\Saifuddin\Documents\StandardEbooks_PDFs" --batch-size 100 --delay 20 --loop --interval 1800 --convert-pdf >> "C:\Users\Saifuddin\Documents\StandardEbooks_PDFs\logs\daemon_stdout.log" 2>&1
