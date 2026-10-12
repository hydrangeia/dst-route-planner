@echo off
setlocal
cd /d "%~dp0"
python route_planner.py --ui %*
if errorlevel 1 pause
