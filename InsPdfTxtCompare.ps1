# PDF Text Compare Tool - EXE Build Script
# This script bundles resources and sets environment variables for the application.

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  PDF Text Compare Tool - Build Process   " -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# 1. Get Build Info
$ver = Read-Host "Step 1: Enter Version Number (e.g. 1.1.2)"
$relDate = Read-Host "Step 2: Enter Release Date (e.g. 2026-01-05)"

# 2. Set Environment Variables for Injection
$env:PDF_COMPARE_VERSION = $ver
$env:PDF_COMPARE_RELEASE_DATE = $relDate

# 3. Define Project Settings
$scriptName = "pdf_text_compare_posid.py"
$exeName = "PDF_Text_Compare_v$ver"
$iconFile = "posid_logo.ico"
$logoFile = "posid_logo.png"

# Check if required files exist
if (-not (Test-Path $scriptName)) {
    Write-Host "Error: $scriptName not found!" -ForegroundColor Red
    exit
}
if (-not (Test-Path $iconFile)) {
    Write-Host "Warning: $iconFile not found for application icon." -ForegroundColor Yellow
}
if (-not (Test-Path $logoFile)) {
    Write-Host "Warning: $logoFile not found for internal dialogs." -ForegroundColor Yellow
}

Write-Host "`nStep 3: Cleaning up old build folders..." -ForegroundColor Yellow
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }

# 4. Run PyInstaller
Write-Host "`nStep 4: Starting PyInstaller build process..." -ForegroundColor Green
Write-Host "Please wait while bundling components into one file..." -ForegroundColor White

# Parameters Explanation:
# --noconsole: No CMD window popup
# --onefile: Bundles everything into a single EXE
# --add-data: Includes the resource files inside the EXE (Crucial for icons and logos)
# --icon: Sets the application icon (Explorer view)

pyinstaller --noconsole --onefile `
    --icon=$iconFile `
    --add-data "$iconFile;." `
    --add-data "$logoFile;." `
    --name $exeName `
    $scriptName

# 5. Result
if ($LASTEXITCODE -eq 0) {
    Write-Host "`n==========================================" -ForegroundColor Green
    Write-Host "  Build Success! EXE is in the 'dist' folder." -ForegroundColor Green
    Write-Host "  File Name: $exeName.exe" -ForegroundColor White
    Write-Host "==========================================" -ForegroundColor Green
} else {
    Write-Host "`nBuild Failed. Please check the error messages above." -ForegroundColor Red
}

pause