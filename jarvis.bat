@echo off
rem Uruchamia Jarvisa w tle, bez okna konsoli (jarvis.pyw przez pythonw) i od razu się zamyka.
rem Dodatkowe argumenty (np. --browser) są przekazywane dalej. Logi: data\jarvis.log.
rem Z logami na ekranie (np. do szukania błędów): py -m jarvis
start "" pyw "%~dp0jarvis.pyw" %*
