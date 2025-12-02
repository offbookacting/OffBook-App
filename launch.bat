@echo off
REM Cross-platform launcher for Off Book / Scene Partner (Windows version)
REM This batch file works on Windows

cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe main.py %*
) else (
    python main.py %*
)

