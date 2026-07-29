@echo off
python run_mvp.py calculate --config config\pmp23607_user.yaml --output results\PMP23607_GBT40432_ADC_Sensing_Design_v0p3.xlsx --json results\PMP23607_GBT40432_ADC_Sensing_Design_v0p3.json
set RC=%ERRORLEVEL%
echo.
echo Exit code: %RC%
pause
exit /b %RC%
