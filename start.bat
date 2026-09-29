@echo off
setlocal
cd /d "%~dp0"
if /i "%~1"=="--update" goto update
if not exist ".venv\Scripts\python.exe" goto setup
".venv\Scripts\python.exe" -c "from importlib.metadata import version; version('audio2text')" >nul 2>&1
if errorlevel 1 goto setup
goto launch

:setup
echo Audio2Text needs its initial dependency setup.
choice /c YN /n /m "Download and install the required dependencies now? [Y/N] "
if errorlevel 2 exit /b 0
if errorlevel 1 goto install
exit /b 1

:install
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 goto error
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto error
goto launch

:update
if not exist ".venv\Scripts\python.exe" goto setup
echo This will check online and install available updates allowed by the project requirements.
choice /c YN /n /m "Update dependencies now? [Y/N] "
if errorlevel 2 exit /b 0
if errorlevel 1 goto upgrade
exit /b 1

:upgrade
".venv\Scripts\python.exe" -m pip install --upgrade -r requirements.txt
if errorlevel 1 goto error
echo Dependency update complete.
pause
exit /b 0

:launch
".venv\Scripts\python.exe" app.py
if errorlevel 1 goto error
exit /b 0

:error
echo Setup or application failed. See the error above.
echo To retry dependency installation or updates, run update.bat.
pause
exit /b 1
