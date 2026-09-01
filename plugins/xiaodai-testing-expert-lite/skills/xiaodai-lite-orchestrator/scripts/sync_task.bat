@echo off
setlocal
set "BIZ_LINE=%~1"
if not defined BIZ_LINE exit /b 2
set "PYTHONIOENCODING=utf-8"
set "PY_EXE="
set "PY_ARGS="

if defined VIRTUAL_ENV if exist "%VIRTUAL_ENV%\Scripts\python.exe" set "PY_EXE=%VIRTUAL_ENV%\Scripts\python.exe"
if not defined PY_EXE if exist "%ProgramData%\miniconda3\python.exe" set "PY_EXE=%ProgramData%\miniconda3\python.exe"
if not defined PY_EXE if exist "%ProgramData%\Anaconda3\python.exe" set "PY_EXE=%ProgramData%\Anaconda3\python.exe"
if not defined PY_EXE if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PY_EXE=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not defined PY_EXE if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PY_EXE if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "PY_EXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not defined PY_EXE if exist "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" set "PY_EXE=%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
if not defined PY_EXE for /f "delims=" %%I in ('where python.exe 2^>nul') do if not defined PY_EXE set "PY_EXE=%%~fI"
if not defined PY_EXE if exist "%SystemRoot%\py.exe" set "PY_EXE=%SystemRoot%\py.exe"& set "PY_ARGS=-3"

set "LOG_DIR=%USERPROFILE%\.workbuddy\data\time-tracking\%BIZ_LINE%"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1
set "LOG_FILE=%LOG_DIR%\sync_log.txt"
if not defined PY_EXE echo ERROR: Python 3 was not found.>>"%LOG_FILE%"& exit /b 9009

set "SYNC_SCRIPT=%~dp0..\..\time-tracking-skill\scripts\sync_to_mysql.py"
if not exist "%SYNC_SCRIPT%" echo ERROR: sync_to_mysql.py was not found.>>"%LOG_FILE%"& exit /b 2
"%PY_EXE%" %PY_ARGS% "%SYNC_SCRIPT%" --biz-line "%BIZ_LINE%" >>"%LOG_FILE%" 2>&1
exit /b %ERRORLEVEL%
