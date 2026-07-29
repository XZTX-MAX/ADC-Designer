@echo off
python run_mvp.py calculate --config config\three_phase_22kw_template.yaml --output results\Three_Phase_22kW_GBT40432_ADC_Sensing_Design_v0p3.xlsx --json results\Three_Phase_22kW_GBT40432_ADC_Sensing_Design_v0p3.json
set RC=%ERRORLEVEL%
echo.
echo Exit code: %RC%
pause
exit /b %RC%
