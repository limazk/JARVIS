@echo off
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py) || (set PY=python)
start "ROTINA servidor" %PY% server.py --no-browser
timeout /t 3 >nul
echo.
echo ===========================================================
echo  Procure abaixo a linha com  https://....trycloudflare.com
echo  Esse e o link pra abrir na faculdade (entra com sua senha).
echo  Feche esta janela = o link para de funcionar na hora.
echo ===========================================================
echo.
cloudflared tunnel --url http://localhost:8765
pause
