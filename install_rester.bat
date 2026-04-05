@echo off
setlocal

echo ============================================
echo   RESTer Installer
echo ============================================
echo.

:: Target install directory
set "INSTALL_DIR=%APPDATA%\pyRevit\Extensions\RESTer"
set "REPO_URL=https://github.com/jedbjorn/RESTer/archive/refs/heads/main.zip"
set "TEMP_ZIP=%TEMP%\RESTer_download.zip"
set "TEMP_EXTRACT=%TEMP%\RESTer_extract"

:: Check if pyRevit Extensions folder exists
if not exist "%APPDATA%\pyRevit\Extensions" (
    echo ERROR: pyRevit Extensions folder not found.
    echo Expected: %APPDATA%\pyRevit\Extensions
    echo.
    echo Please install pyRevit first: https://github.com/pyrevitlabs/pyRevit
    pause
    exit /b 1
)

:: Check if already installed
if exist "%INSTALL_DIR%" (
    echo RESTer is already installed at:
    echo   %INSTALL_DIR%
    echo.
    set /p OVERWRITE="Overwrite existing installation? (Y/N): "
    if /i not "%OVERWRITE%"=="Y" (
        echo Installation cancelled.
        pause
        exit /b 0
    )
    echo Removing existing installation...
    rmdir /s /q "%INSTALL_DIR%"
)

:: Try git clone first, fall back to zip download
echo.
where git >nul 2>&1
if %errorlevel%==0 (
    echo Downloading RESTer via git...
    git clone https://github.com/jedbjorn/RESTer.git "%INSTALL_DIR%" 2>&1
    if errorlevel 1 (
        echo Git clone failed. Trying zip download...
        goto :zip_download
    )
    goto :post_install
)

:zip_download
echo Downloading RESTer via zip...

:: Download zip
where curl >nul 2>&1
if %errorlevel%==0 (
    curl -L -o "%TEMP_ZIP%" "%REPO_URL%"
) else (
    powershell -Command "Invoke-WebRequest -Uri '%REPO_URL%' -OutFile '%TEMP_ZIP%'"
)

if not exist "%TEMP_ZIP%" (
    echo ERROR: Download failed.
    pause
    exit /b 1
)

:: Extract zip
echo Extracting...
if exist "%TEMP_EXTRACT%" rmdir /s /q "%TEMP_EXTRACT%"
powershell -Command "Expand-Archive -Path '%TEMP_ZIP%' -DestinationPath '%TEMP_EXTRACT%' -Force"

:: The zip extracts to RESTer-main/ — move contents to install dir
if exist "%TEMP_EXTRACT%\RESTer-main" (
    xcopy "%TEMP_EXTRACT%\RESTer-main" "%INSTALL_DIR%\" /E /I /Y >nul
) else (
    echo ERROR: Unexpected zip structure.
    pause
    exit /b 1
)

:: Cleanup temp files
del "%TEMP_ZIP%" 2>nul
rmdir /s /q "%TEMP_EXTRACT%" 2>nul

:post_install
echo.
echo RESTer installed to:
echo   %INSTALL_DIR%
echo.

:: Install Python dependencies
echo Installing Python dependencies...
pip install pywebview >nul 2>&1
if errorlevel 1 (
    echo WARNING: Could not install pywebview. You may need to install it manually.
    echo   Run: pip install pywebview
    echo.
)

:: Create launcher in Documents
set "DOCS_DIR=%USERPROFILE%\Documents"
set "LAUNCHER=%DOCS_DIR%\RESTer Profile Loader.bat"

echo @echo off > "%LAUNCHER%"
echo python "%INSTALL_DIR%\app\profile_selector.py" >> "%LAUNCHER%"

echo Created launcher:
echo   %LAUNCHER%
echo.

:: Create profiles directory if it doesn't exist
if not exist "%INSTALL_DIR%\app\profiles" mkdir "%INSTALL_DIR%\app\profiles"
if not exist "%INSTALL_DIR%\icons" mkdir "%INSTALL_DIR%\icons"

echo ============================================
echo   Installation complete!
echo ============================================
echo.
echo To use RESTer:
echo   1. Reload pyRevit in Revit to see the Admin tab
echo   2. Double-click "RESTer Profile Loader.bat" in Documents
echo      to manage profiles outside of Revit
echo.
pause
