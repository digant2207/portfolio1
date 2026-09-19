@echo off
title Smart Money 200 DMA Paper Trading Terminal
cd /d "%~dp0"
echo =======================================================
echo Starting Smart Money 200 DMA Paper Trading Terminal...
echo Dashboard: http://127.0.0.1:8000
echo =======================================================
.\.venv\Scripts\python.exe run.py
pause
