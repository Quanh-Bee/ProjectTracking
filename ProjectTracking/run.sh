#!/bin/bash

echo "========================================"
echo "Face Tracking System - Local Run"
echo "========================================"
echo

# Activate virtual environment
echo "Activating virtual environment..."
source face_tracking_env/bin/activate

echo
echo "========================================"
echo "Starting Face Tracking System"
echo "========================================"
echo

python main.py
