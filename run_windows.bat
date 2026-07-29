@echo off
python run_mvp.py calculate --config config\pmp23607_user.yaml --output results\PMP23607_ADC_Sensing_Design.xlsx --json results\PMP23607_ADC_Sensing_Design.json
set RC=%ERRORLEVEL%
echo.
echo Exit code: %RC%
pause
exit /b %RC%
