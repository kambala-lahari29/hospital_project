@echo off
echo ========================================================
echo   Pushing Hospital Analytics Project to GitHub...
echo ========================================================
cd /d "%~dp0"
git push -u origin main
echo.
echo ========================================================
echo   Push Complete! Press any key to exit.
echo ========================================================
pause
