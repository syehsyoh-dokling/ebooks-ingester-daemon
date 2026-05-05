$ErrorActionPreference = 'Stop'

$downloadUrl = "https://calibre-ebook.com/download_windows64"
$installerPath = "$env:TEMP\calibre-installer.exe"

Write-Host "Downloading Calibre..." -ForegroundColor Cyan
Invoke-WebRequest -Uri $downloadUrl -OutFile $installerPath -UseBasicParsing

Write-Host "Running installer..." -ForegroundColor Cyan
Start-Process -FilePath $installerPath -Wait

Write-Host "Checking ebook-convert..." -ForegroundColor Cyan
$possiblePaths = @(
    "C:\Program Files\Calibre2\ebook-convert.exe",
    "C:\Program Files (x86)\Calibre2\ebook-convert.exe"
)

$ebookConvert = $possiblePaths | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($ebookConvert) {
    Write-Host "Found: $ebookConvert" -ForegroundColor Green
    & $ebookConvert --version
} else {
    Write-Host "Calibre installed, but ebook-convert.exe was not found in the default folder." -ForegroundColor Yellow
    Write-Host "Please check the installation manually." -ForegroundColor Yellow
}