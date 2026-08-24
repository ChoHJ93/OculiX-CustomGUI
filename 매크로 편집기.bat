@echo off
rem OculiX Macro Editor launcher.
rem
rem Asks for administrator rights and relaunches itself through UAC, because
rem the editor drives macros that must click on elevated windows such as
rem Hyper-V Manager. Windows blocks synthetic input from a normal process to
rem an elevated window, so the editor has to run at the same level.
rem
rem   "macro editor.bat"                normal start (asks for admin)
rem   "macro editor.bat" noadmin        start without admin
rem   "macro editor.bat" debug          console attached, errors visible
rem   "macro editor.bat" debug noadmin  console, no admin
rem
rem Uses pythonw so no console window stays behind.
rem If the editor cannot start, the reason is written to Logs\editor-crash.log.
rem Content is kept ASCII on purpose - batch files are read in the OEM codepage.

setlocal
set "ROOT=%~dp0"
set "EDITOR=%ROOT%Tools\MacroEditor\macro_editor.py"
set "LOGDIR=%ROOT%Logs"
set "WHOAMI=%SystemRoot%\System32\whoami.exe"
set "FINDSTR=%SystemRoot%\System32\findstr.exe"

if not exist "%EDITOR%" (
    echo Editor not found: %EDITOR%
    echo.
    pause
    exit /b 1
)

if not exist "%LOGDIR%" mkdir "%LOGDIR%"

rem Read the arguments. "noadmin" and "elevated" are flags and may appear in
rem any position; the first remaining argument is the mode. "elevated" is set
rem by the relaunch below and guarantees we never ask for rights twice, even
rem if the check further down were to misfire.
set "MODE="
set "SKIPADMIN="
:parse
if "%~1"=="" goto parsed
if /i "%~1"=="noadmin" goto parse_flag
if /i "%~1"=="elevated" goto parse_flag
set "MODE=%~1"
goto parse_next
:parse_flag
set "SKIPADMIN=1"
:parse_next
shift
goto parse
:parsed

if defined SKIPADMIN goto run

rem High (12288) or System (16384) integrity means we are already elevated.
rem Matching on the SID keeps this working on non-English Windows, and the
rem full paths keep a whoami.exe from some other toolchain on PATH out of it -
rem a wrong answer here would loop the UAC prompt forever.
"%WHOAMI%" /groups | "%FINDSTR%" /C:"S-1-16-12288" /C:"S-1-16-16384" >nul 2>&1
if not errorlevel 1 goto run

rem Not elevated yet. Relaunch through UAC.
rem The path travels in an environment variable rather than on the command
rem line so that spaces and non-ASCII characters in it survive intact.
set "SELF=%~f0"
set "SELFARGS=elevated"
if defined MODE set "SELFARGS=%MODE% elevated"
powershell -NoProfile -Command "try { Start-Process -FilePath $env:SELF -ArgumentList $env:SELFARGS -Verb RunAs } catch { exit 1 }"
if errorlevel 1 (
    echo.
    echo Administrator rights were not granted, so the editor was not started.
    echo Run it with the "noadmin" argument to start without them.
    echo.
    pause
)
exit /b 0

:run
if /i "%MODE%"=="debug" goto debug

where pythonw >nul 2>&1
if errorlevel 1 goto no_python

rem No redirection here on purpose. A redirect on a start line applies to start
rem itself, never to pythonw, so it captured nothing - and it held the log file
rem locked for as long as the editor was running.
start "" pythonw "%EDITOR%"
exit /b 0

:debug
where python >nul 2>&1
if errorlevel 1 goto no_python
echo Running the editor with a console attached.
echo Working directory: %CD%
"%WHOAMI%" /groups | "%FINDSTR%" /C:"S-1-16-"
where python
echo.
python "%EDITOR%"
echo.
echo Editor exited with code %ERRORLEVEL%
pause
exit /b 0

:no_python
where python >nul 2>&1
if errorlevel 1 (
    echo Python was not found on PATH.
    echo Install Python 3, or run the editor directly:
    echo   python "%EDITOR%"
    echo.
    pause
    exit /b 1
)
rem Fall back to python.exe; the console stays open so errors are visible.
python "%EDITOR%"
if errorlevel 1 pause
exit /b 0
