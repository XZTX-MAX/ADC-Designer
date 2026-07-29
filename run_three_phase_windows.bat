@echo off
python run_mvp.py calculate --config config\three_phase_22kw_template.yaml --output results\Three_Phase_22kW_ADC_Sensing_Design.xlsx --json results\Three_Phase_22kW_ADC_Sensing_Design.json
set RC=%ERRORLEVEL%
echo.
echo Exit code: %RC%
pause
exit /b %RC%
