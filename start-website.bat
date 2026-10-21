@echo off
rem Double-click to start the Open Data Explorer website.
rem It opens in your browser automatically.
rem Close this window (or press Ctrl+C) to stop the website.

title Open Data Explorer
cd /d "%~dp0"

rem This file must sit next to publicdata.py, with server.py in webapp\
if not exist "webapp\server.py" goto missing_files
if not exist "publicdata.py" goto missing_files

rem Find a working Python.
rem "where python" is not enough: Windows ships a 0-byte Microsoft Store stub
rem named python.exe, so the check passes on machines with no Python at all
rem and the Store opens instead. Actually running Python is the only real test.
set "PY="
py -3 -c "import sys" >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if defined PY goto run

python -c "import sys" >nul 2>nul
if not errorlevel 1 set "PY=python"
if defined PY goto run

echo.
echo Python was not found on this computer.
echo.
echo Install Python 3.9 or later from https://www.python.org/downloads/
echo During setup, tick "Add python.exe to PATH", then run this file again.
echo.
pause
exit /b 1

:missing_files
echo.
echo This file is in the wrong place, or some files are missing.
echo.
echo Expected next to this file:
echo    publicdata.py
echo    webapp\server.py
echo    webapp\index.html
echo.
pause
exit /b 1

:run
rem server.py picks a free port and opens the browser itself
%PY% webapp\server.py

echo.
echo The website has stopped.
pause
