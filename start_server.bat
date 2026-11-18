
@echo off
title GFG AutoSolver PRO Backend

cd /d "C:\Users\Lenovo\Documents\PROJECTS-SHUSHANT\gfg_autosolver_pro_deployment"

echo.
echo =====================================
echo    GFG AutoSolver PRO Backend
echo =====================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Virtual environment not found!
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m uvicorn backend.app:app --reload

pause
