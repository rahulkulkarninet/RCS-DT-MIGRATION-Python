@echo off
echo =====================================
echo  RCS-DT Migration Process Runner
echo =====================================

set "PYTHON_EXE=python"
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=.venv\Scripts\python.exe"

:: Set environment (default: v10)
set ENVIRONMENT=%1
if "%ENVIRONMENT%"=="" set ENVIRONMENT=uat
echo Environment: %ENVIRONMENT%

:: Forward any remaining arguments (e.g. --non-interactive --auto-approve all)
shift
set "EXTRA_ARGS="
:collect_args
if "%~1"=="" goto :args_collected
set "EXTRA_ARGS=%EXTRA_ARGS% %~1"
shift
goto :collect_args
:args_collected
if not "%EXTRA_ARGS%"=="" echo Extra arguments:%EXTRA_ARGS%

:: Basic checks
%PYTHON_EXE% --version >nul 2>&1 || (echo ERROR: Python not found & pause & exit /b 1)
if not exist "Run_Migration.py" (echo ERROR: Run_Migration.py not found & pause & exit /b 1)

:: Install dependencies (user-level)
echo Installing Python dependencies...
%PYTHON_EXE% -m pip install -r requirements.txt --no-warn-script-location >nul 2>&1

:: Run migration Python script
echo Starting migration process...
%PYTHON_EXE% Run_Migration.py %ENVIRONMENT%%EXTRA_ARGS%

echo.
if %errorlevel% equ 0 (
    echo Migration completed successfully!
) else (
    echo Migration failed - check log file
)
echo Log: %USERPROFILE%\migration_process.log
pause