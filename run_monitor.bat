@echo off
cd /d %~dp0
python -m pip install -r requirements.txt
python monitor_5070_ti_v_2.py > monitor-last.log 2>&1
type monitor-last.log
pause
