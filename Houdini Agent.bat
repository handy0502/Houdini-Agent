@echo off
setlocal

rem Houdini Agent desktop launcher.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0houdini_agent\launcher\Agent Launcher.ps1" %*
if errorlevel 1 (
    echo.
    echo Houdini Agent could not start. See the error above.
    pause
    exit /b 1
)

exit /b 0
