@echo off
echo Installing requirements...
pip install -r requirements.txt
echo.
echo Starting optimized build...
python build_optimized.py
echo.
echo Build finished.
pause
