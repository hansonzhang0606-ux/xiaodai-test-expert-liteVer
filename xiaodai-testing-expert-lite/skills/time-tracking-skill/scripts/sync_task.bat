@echo off
REM ============================================================
REM 时间记录同步到 MySQL（通用多业务线版，v5.5）
REM 本文件必须 GBK 编码 + CRLF 换行（schtasks 的 cmd.exe 用 936 读取）
REM 业务线由第 1 个参数 %1 决定（缺省默认：智慧记+运营系统）；
REM   注册任务时在 /tr 末尾传入对应业务线，如 sync_task.bat 效融
REM   支持业务线：效贷 / 泾渭云 / 效融 / 小贷 / 智慧记+运营系统 / AI进销存 / 智慧记零售
REM ============================================================
set "BIZ_LINE=%1"
if "%BIZ_LINE%"=="" set "BIZ_LINE=智慧记+运营系统"
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

REM 探测 Python（优先 python 命令，失败试常见绝对路径）
set "PY_CMD="
where python >nul 2>&1 && set "PY_CMD=python"
if not defined PY_CMD if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY_CMD=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PY_CMD if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PY_CMD=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not defined PY_CMD (
  echo ERROR: 未找到 Python，请安装 Python 3.6+ 并加入 PATH >> "%~dp0sync_log.txt" 2>&1
  exit /b 9009
)

REM 运行同步，日志追加到本地
"%PY_CMD%" sync_to_mysql.py --biz-line %BIZ_LINE% >> "%~dp0sync_log.txt" 2>&1
exit /b %ERRORLEVEL%
