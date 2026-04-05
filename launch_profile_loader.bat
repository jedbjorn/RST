@echo off
echo Installing dependencies...
pip install pywebview
if errorlevel 1 (
    echo.
    echo Failed to install pywebview. Make sure Python and pip are installed.
    pause
    exit /b 1
)
echo.
echo Launching RESTer Profile Selector...
python "%~dp0app\profile_selector.py"
if errorlevel 1 (
    echo.
    echo An error occurred. Check rester.log for details.
    pause
)
