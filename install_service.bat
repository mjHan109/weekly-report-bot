@chcp 65001 >nul 2>&1
@echo off

set BOT_SERVICE=WeeklyReportBot
set TUNNEL_SERVICE=WeeklyReportTunnel
set APP_DIR=%~dp0
:: 후행 슬래시 제거
if "%APP_DIR:~-1%"=="\" set APP_DIR=%APP_DIR:~0,-1%
set UVICORN=C:\Users\D-285\AppData\Local\Programs\Python\Python311\Scripts\uvicorn.exe
set SSH=C:\Windows\System32\OpenSSH\ssh.exe
set LOG_DIR=%APP_DIR%logs
set /p SUBDOMAIN=Serveo subdomain name (영문/숫자만, ex: weeklyreportbot):

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

where nssm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] nssm not found. Run: winget install NSSM.NSSM
    pause
    exit /b 1
)

echo [1/2] Registering uvicorn service...
nssm status %BOT_SERVICE% >nul 2>&1
if not errorlevel 1 (
    nssm stop %BOT_SERVICE% >nul 2>&1
    nssm remove %BOT_SERVICE% confirm
)
nssm install %BOT_SERVICE% "%UVICORN%"
nssm set %BOT_SERVICE% AppParameters "src.main:app --host 0.0.0.0 --port 8001"
nssm set %BOT_SERVICE% AppDirectory "%APP_DIR%"
nssm set %BOT_SERVICE% AppStdout "%LOG_DIR%\uvicorn_stdout.log"
nssm set %BOT_SERVICE% AppStderr "%LOG_DIR%\uvicorn_stderr.log"
nssm set %BOT_SERVICE% AppRotateFiles 1
nssm set %BOT_SERVICE% AppRotateSeconds 86400
nssm set %BOT_SERVICE% AppRotateBytes 10485760
nssm set %BOT_SERVICE% AppExit Default Restart
nssm set %BOT_SERVICE% AppRestartDelay 5000
nssm start %BOT_SERVICE%
echo uvicorn service started.

echo [2/2] Registering Serveo tunnel service...
nssm status %TUNNEL_SERVICE% >nul 2>&1
if not errorlevel 1 (
    nssm stop %TUNNEL_SERVICE% >nul 2>&1
    nssm remove %TUNNEL_SERVICE% confirm
)
nssm install %TUNNEL_SERVICE% "%SSH%"
nssm set %TUNNEL_SERVICE% AppParameters "-o StrictHostKeyChecking=no -o ServerAliveInterval=60 -o ExitOnForwardFailure=yes -R %SUBDOMAIN%:80:localhost:8001 serveo.net"
nssm set %TUNNEL_SERVICE% AppStdout "%LOG_DIR%\tunnel_stdout.log"
nssm set %TUNNEL_SERVICE% AppStderr "%LOG_DIR%\tunnel_stderr.log"
nssm set %TUNNEL_SERVICE% AppExit Default Restart
nssm set %TUNNEL_SERVICE% AppRestartDelay 10000
nssm start %TUNNEL_SERVICE%
echo Tunnel service started.

echo.
echo === Done ===
echo Slack Request URL: https://%SUBDOMAIN%.serveo.net/slack/events
echo Log directory: %LOG_DIR%
echo.
echo Commands:
echo   nssm status %BOT_SERVICE%
echo   nssm status %TUNNEL_SERVICE%
echo   nssm stop %BOT_SERVICE%
echo   nssm stop %TUNNEL_SERVICE%
pause
