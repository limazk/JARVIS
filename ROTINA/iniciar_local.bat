@echo off
title ROTINA - servidor (nao feche)
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py) || (set PY=python)
%PY% --version >nul 2>nul || (
  echo.
  echo [!] Python nao encontrado. Instale em python.org e marque "Add Python to PATH".
  pause & exit /b
)
%PY% server.py
echo.
echo O servidor parou. Veja a mensagem acima.
pause
