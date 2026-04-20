@echo off
echo Stopping Face Tracking System...

REM Kill all Python processes
taskkill /F /IM python.exe 2>nul
taskkill /F /IM pythonw.exe 2>nul

REM Kill processes on port 5000
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5000 ^| findstr LISTENING') do (
    taskkill /F /PID %%a 2>nul
)

echo All processes stopped!
pause
