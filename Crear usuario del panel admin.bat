@echo off
chcp 65001 >nul
title Portal de compromisos SAO6 - usuario del panel /admin
cd /d "%~dp0"
set PYTHONDONTWRITEBYTECODE=1
set PY=
for %%P in ("%USERPROFILE%\anaconda3\python.exe" "%USERPROFILE%\Anaconda3\python.exe" "C:\ProgramData\anaconda3\python.exe" "C:\ProgramData\Anaconda3\python.exe" "%LOCALAPPDATA%\anaconda3\python.exe") do (
  if exist %%P if not defined PY set PY=%%P
)
if not defined PY set PY=python
echo Crea el usuario y la contrasena para entrar a http://localhost:8051/admin
echo ^(primero debe haberse ejecutado una vez "Iniciar prueba1.bat"^).
echo.
%PY% manage.py createsuperuser
pause
