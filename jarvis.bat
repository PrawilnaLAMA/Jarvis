@echo off
rem Uruchamia Jarvisa z katalogu, w którym leży ten plik (dodatkowe argumenty, np. --browser, są przekazywane dalej)
cd /d "%~dp0"
py -m jarvis %*
if errorlevel 1 pause
