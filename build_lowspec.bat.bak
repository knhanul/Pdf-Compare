@echo off
echo ========================================
echo PDF Text Compare Program Build
echo Low-Spec PC Optimized Version
echo POSID System Quality Team
echo ========================================
echo.

REM --- ?? ? ?? ?? ---
set /p VERSION="Enter version (e.g. 1.3.1): "
for /f "tokens=1-3 delims=- " %%a in ('echo %date%') do (
    set RELEASE_DATE=%%a-%%b-%%c
)

echo.
echo [Build Configuration]
echo Version: %VERSION%
echo Release Date: %RELEASE_DATE%
echo Optimization: Low-Spec PC
echo.

REM --- ?? ?? ?? (??) ---
set PDF_COMPARE_VERSION=%VERSION%
set PDF_COMPARE_RELEASE_DATE=%RELEASE_DATE%

REM --- ?? ?? ?? ---
if exist "dist" (
    echo Cleaning previous build files...
    rmdir /s /q dist
)

echo.
echo Starting build (Low-Spec Optimized)...
echo - No UPX compression (antivirus compatibility)
echo - Optimize imports (faster startup)
echo - Console disabled (GUI only)
echo - Build cache cleared (--clean)
echo.

REM --- PyInstaller ?? (?? ?? ?? ??) ---
pyinstaller --clean --onefile --windowed --noupx --optimize=2 --icon=posid_logo.ico --add-data "posid_logo.png;." --name "PDF_Compare_v%VERSION%" --hidden-import=PyQt6.QtCore --hidden-import=PyQt6.QtGui --hidden-import=PyQt6.QtWidgets --hidden-import=fitz --exclude-module=tkinter --exclude-module=matplotlib --exclude-module=numpy --exclude-module=scipy --exclude-module=PyQt5 pdf_text_compare_posid.py

REM --- ?? ?? ?? (GOTO ???? ??) ---
if %ERRORLEVEL% EQU 0 (
    GOTO BUILD_SUCCESS
) else (
    GOTO BUILD_FAILURE
)

:BUILD_SUCCESS
    echo.
    echo ========================================
    echo Build Complete!
    echo ========================================
    echo.
    echo Executable location: dist\PDF_Compare_v%VERSION%.exe
    echo.
    
    REM Display file information
    for %%F in (dist\*.exe) do (
        echo Filename: %%~nxF
        echo Size: %%~zF bytes
        echo Path: %%~fF
    )
    
    echo.
    echo [Pre-Distribution Checklist]
    echo - Test on low-spec PC (2GB RAM, old CPU)
    echo - Test on Windows 10, 11
    echo - Test with antivirus software
    echo - Test in Korean path
    echo - Test without admin rights
    echo.
    echo [User Instructions]
    echo - Antivirus exception may be required
    echo - VC++ Redistributable may be required
    echo   Download: https://aka.ms/vs/17/release/vc_redist.x64.exe
    echo.
    GOTO END

:BUILD_FAILURE
    echo.
    echo ========================================
    echo Build Failed!
    echo ========================================
    echo.
    echo Troubleshooting:
    echo 1. Check PyInstaller: pip install pyinstaller
    echo 2. Install libraries: pip install PyQt6 PyMuPDF Pillow
    echo 3. Check posid_logo.ico exists
    echo 4. Check posid_logo.png exists
    echo.
    GOTO END

:END
echo.
pause