@echo off
python "%~dp0app\profile_selector.py"
if errorlevel 1 (
    echo.
    echo An error occurred. Check rester.log for details.
    pause
)
