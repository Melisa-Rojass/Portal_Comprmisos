@echo off
chcp 65001 >nul
title Portal de compromisos SAO6 (Django) - Activar inicio automatico
cd /d "%~dp0"
set "CARPETA=%~dp0"
set "PYW="
for %%P in ("%USERPROFILE%\anaconda3\pythonw.exe" "%USERPROFILE%\Anaconda3\pythonw.exe" "C:\ProgramData\anaconda3\pythonw.exe" "C:\ProgramData\Anaconda3\pythonw.exe" "%LOCALAPPDATA%\anaconda3\pythonw.exe") do (
  if exist %%P if not defined PYW set "PYW=%%~P"
)
if not defined PYW (
  for /f "delims=" %%W in ('where pythonw 2^>nul') do if not defined PYW set "PYW=%%W"
)
if not defined PYW (
  echo No encontre Python ^(Anaconda^) en este equipo.
  pause
  exit /b
)

set "INICIO=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Portal de compromisos SAO6.bat"
(
  echo @echo off
  echo chcp 65001 ^>nul
  echo rem Enciende el Portal de compromisos SAO6 al iniciar sesion
  echo for /l %%%%i in ^(1,1,60^) do if not exist "%CARPETA%manage.py" timeout /t 5 /nobreak ^>nul
  echo set PYTHONDONTWRITEBYTECODE=1
  echo cd /d "%CARPETA%"
  echo start "" "%PYW%" manage.py iniciar
) > "%INICIO%"

rem Acceso directo (link) en el escritorio con el icono del portal
set "DESK="
for /f "tokens=2,*" %%a in ('reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders" /v Desktop 2^>nul ^| findstr /i Desktop') do set "DESK=%%b"
if defined DESK call set "DESK=%DESK%"
if not defined DESK set "DESK=%USERPROFILE%\Desktop"
(
  echo [InternetShortcut]
  echo URL=http://localhost:8050
  echo IconFile=%CARPETA%portal.ico
  echo IconIndex=0
) > "%DESK%\Compromisos SAO6.url"

echo Apagando lo que este usando el puerto 8050 ^(portal anterior^)...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8050 " ^| findstr LISTENING') do taskkill /PID %%a /F >nul 2>nul
timeout /t 2 /nobreak >nul
set PYTHONDONTWRITEBYTECODE=1
set "PY=%PYW:pythonw.exe=python.exe%"
echo Preparando la base de datos...
"%PY%" manage.py migrate --noinput -v 0
echo Encendiendo el portal...
start "" "%PYW%" manage.py iniciar
timeout /t 12 /nobreak >nul
curl -s -o nul -w "%%{http_code}" http://localhost:8050/manifest.json > "%TEMP%\portal_estado.txt" 2>nul
set /p ESTADO=<"%TEMP%\portal_estado.txt"
echo.
if "%ESTADO%"=="200" (
  echo ============================================================
  echo  LISTO. El portal ^(Django^) esta encendido y se encendera solo cada vez
  echo  que inicies sesion en este computador.
  echo.
  echo  Link para los responsables:  http://%COMPUTERNAME%:8050
  echo  En este computador:          http://localhost:8050
  echo  ^(tambien quedo el icono Compromisos SAO6 en tu escritorio^)
  echo ============================================================
  start "" http://localhost:8050
) else (
  echo El inicio automatico quedo configurado, pero el portal no respondio.
  echo Abre el archivo portal.log de esta carpeta y envia lo que dice.
)
echo.
pause
