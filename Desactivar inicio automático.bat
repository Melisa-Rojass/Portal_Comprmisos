@echo off
title Portal de compromisos SAO6 - Desactivar
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Portal de compromisos SAO6.bat" 2>nul
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8050 " ^| findstr LISTENING') do taskkill /PID %%a /F >nul
echo Listo. El portal se apago y ya no se encendera solo.
pause
