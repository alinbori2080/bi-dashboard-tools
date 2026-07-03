@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONUTF8=1"
set "PORT=8767"
set "APP_URL=http://127.0.0.1:%PORT%/"

netstat -ano -p tcp | findstr "127.0.0.1:%PORT%" | findstr "LISTENING" >nul
if not errorlevel 1 (
  call :open_browser
  goto :eof
)

:port_free
where py >nul 2>nul
if not errorlevel 1 (
  call :open_browser
  py -3 -B server.py %PORT%
  goto :eof
)

where python >nul 2>nul
if not errorlevel 1 (
  call :open_browser
  python -B server.py %PORT%
  goto :eof
)

set "CODEX_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%CODEX_PY%" (
  call :open_browser
  "%CODEX_PY%" -B server.py %PORT%
  goto :eof
)

echo Python was not found. Please install Python or run server.py in Codex.
pause
goto :eof

:open_browser
echo Opening %APP_URL%
start "" "%APP_URL%"
exit /b 0
