@echo off
echo ========================================
echo Face Tracking System - Local Run
echo ========================================
echo.

echo Activating virtual environment...
call face_tracking_env\Scripts\activate.bat

echo.
echo ========================================
echo Starting Face Tracking System
echo ========================================
echo.

python main.py

pause
