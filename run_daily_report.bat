@echo off
chcp 65001 > nul
cd /d X:\Private\Codex\monitor-5070ti

echo ========================================
echo RTX 5070 Ti Monitor - daily Telegram report
echo ========================================
echo.

python monitor_5070_ti_v_2.py --browser --daily-report

echo.
echo ========================================
echo Done. Opening results.md...
echo ========================================

if exist results.md (
    start "" "C:\Program Files\Notepad++\notepad++.exe" results.md
) else (
    echo results.md not found
)

echo.
pause