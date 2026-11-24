@echo off
chcp 65001 >nul
title Portal de compromisos SAO6 - prueba1 (Django)
cd /d "%~dp0"
set PYTHONDONTWRITEBYTECODE=1
set PY=
for %%P in ("%USERPROFILE%\anaconda3\python.exe" "%USERPROFILE%\Anaconda3\python.exe" "C:\ProgramData\anaconda3\python.exe" "C:\ProgramData\Anaconda3\python.exe" "%LOCALAPPDATA%\anaconda3\python.exe") do (
  if exist %%P if not defined PY set PY=%%P
)
if not defined PY set PY=python

%PY% -c "import django" 2>nul
if errorlevel 1 (
  echo Instalando Django ^(solo la primera vez^)...
  %PY% -m pip install "django>=4.2,<6"
  if errorlevel 1 (
    echo.
    echo No se pudo instalar Django. Revisa la conexion a internet o pide a Sistemas que lo instale.
    pause
    exit /b
  )
)

echo Preparando la base de datos...
%PY% manage.py makemigrations compromisos --noinput -v 0
%PY% manage.py migrate --noinput -v 0
%PY% manage.py importar_json
%PY% manage.py iniciar
echo.
echo El portal se detuvo. Revisa el mensaje de arriba.
pause
