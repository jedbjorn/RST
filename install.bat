@echo off
setlocal EnableDelayedExpansion

rem ============================================================
rem  RST - Dependency Installer
rem  Installs: Python Install Manager (py), Python 3.12, pywebview
rem  Does NOT install the RST extension itself - use pyRevit for that:
rem    pyRevit tab -> Extensions -> Add Extension -> paste the repo URL
rem ============================================================

title RST - Dependency Installer

echo.
echo ============================================================
echo   RST Dependency Installer
echo ============================================================
echo.
echo This will install:
echo   1. Python Install Manager (if missing)
echo   2. Python 3.12          (if missing)
echo   3. pywebview            (always upgraded)
echo.
echo Runs as the current user. No admin required.
echo.
pause

set "STEP1=SKIP"
set "STEP2=SKIP"
set "STEP3=SKIP"
set "STEP4=SKIP"
set "PYREVIT=UNKNOWN"

rem ---------- Step 0: winget present? ----------
echo.
echo [0/4] Checking for winget...
where winget >nul 2>&1
if errorlevel 1 (
    echo   FAIL: winget not found.
    echo   Install "App Installer" from the Microsoft Store, then re-run this script:
    echo   https://apps.microsoft.com/detail/9NBLGGH4NNS1
    goto :summary_fail
)
echo   OK: winget present.

rem ---------- Step 1: Python Install Manager ----------
echo.
echo [1/4] Python Install Manager...
where py >nul 2>&1
if %errorlevel%==0 (
    echo   Already installed. Skipping.
    set "STEP1=SKIP"
) else (
    echo   Installing via winget (9NQ7512CXL7T)...
    winget install --id 9NQ7512CXL7T --accept-source-agreements --accept-package-agreements --silent
    if errorlevel 1 (
        echo   FAIL: winget install returned an error.
        set "STEP1=FAIL"
        goto :summary
    )
    rem Refresh PATH for this session so 'py' is found below.
    call :refresh_path
    where py >nul 2>&1
    if errorlevel 1 (
        echo   WARN: py not on PATH yet. You may need to open a new terminal and re-run.
        set "STEP1=FAIL"
        goto :summary
    )
    set "STEP1=OK"
)

rem ---------- Step 2: Python 3.12 ----------
echo.
echo [2/4] Python 3.12...
py -3.12 -V >nul 2>&1
if %errorlevel%==0 (
    for /f "tokens=*" %%v in ('py -3.12 -V 2^>^&1') do echo   Already installed: %%v. Skipping.
    set "STEP2=SKIP"
) else (
    echo   Installing Python 3.12 via py manager...
    py install 3.12
    if errorlevel 1 (
        echo   FAIL: py install 3.12 returned an error.
        set "STEP2=FAIL"
        goto :summary
    )
    py -3.12 -V >nul 2>&1
    if errorlevel 1 (
        echo   FAIL: Python 3.12 not resolvable after install.
        set "STEP2=FAIL"
        goto :summary
    )
    set "STEP2=OK"
)

rem ---------- Step 3: pywebview ----------
echo.
echo [3/4] pywebview...
py -3.12 -m pip install --upgrade pywebview
if errorlevel 1 (
    echo   FAIL: pip install pywebview returned an error.
    set "STEP3=FAIL"
    goto :summary
)
set "STEP3=OK"

rem ---------- Step 4: Verify pywebview importable ----------
echo.
echo [4/4] Verifying pywebview import...
py -3.12 -c "import webview; print('pywebview', webview.__version__)" 2>nul
if errorlevel 1 (
    echo   FAIL: pywebview installed but not importable.
    set "STEP4=FAIL"
    goto :summary
)
set "STEP4=OK"

rem ---------- Soft check: pyRevit ----------
echo.
echo Checking for pyRevit...
if exist "%APPDATA%\pyRevit" (
    set "PYREVIT=FOUND"
    echo   OK: pyRevit appears to be installed.
) else (
    set "PYREVIT=MISSING"
    echo   WARN: pyRevit not detected at %%APPDATA%%\pyRevit.
    echo         Install pyRevit 4.8+ before adding the RST extension.
    echo         https://github.com/pyrevitlabs/pyRevit
)

:summary
echo.
echo ============================================================
echo   Summary
echo ============================================================
echo   Python Install Manager : %STEP1%
echo   Python 3.12            : %STEP2%
echo   pywebview install      : %STEP3%
echo   pywebview import check : %STEP4%
echo   pyRevit detected       : %PYREVIT%
echo ============================================================

if "%STEP1%"=="FAIL" goto :summary_fail
if "%STEP2%"=="FAIL" goto :summary_fail
if "%STEP3%"=="FAIL" goto :summary_fail
if "%STEP4%"=="FAIL" goto :summary_fail

echo.
echo SUCCESS. Dependencies are ready.
echo.
echo Next step - install the RST extension via pyRevit:
echo   1. Open Revit
echo   2. pyRevit tab -^> Extensions -^> Add Extension
echo   3. Paste: https://github.com/jedbjorn/RST
echo   4. Reload pyRevit
echo.
pause
endlocal
exit /b 0

:summary_fail
echo.
echo FAILED. Review the errors above and re-run this script.
echo.
pause
endlocal
exit /b 1

rem ---------- helpers ----------
:refresh_path
for /f "usebackq tokens=2,*" %%A in (`reg query "HKCU\Environment" /v PATH 2^>nul ^| findstr /i "PATH"`) do set "USER_PATH=%%B"
for /f "usebackq tokens=2,*" %%A in (`reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v PATH 2^>nul ^| findstr /i "PATH"`) do set "SYS_PATH=%%B"
set "PATH=%SYS_PATH%;%USER_PATH%"
exit /b 0
