@echo off
echo Checking running processes...

echo.
echo Python processes:
tasklist | findstr python

echo.
echo Processes on port 5000:
netstat -ano | findstr :5000

echo.
echo Press any key to continue...
pause >nul
