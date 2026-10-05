@echo off
REM ============================================================
REM  Jarvis - cria um atalho na Area de Trabalho para o Jarvis.exe
REM  (ETAPA EXE-3). Rode isto DEPOIS do build.bat, de dentro da
REM  pasta que contem o Jarvis.exe (a pasta "dist").
REM ============================================================

if not exist "Jarvis.exe" (
    echo [ERRO] Rode este arquivo de dentro da pasta que contem o Jarvis.exe
    echo        ^(normalmente a pasta "dist" criada pelo build.bat^).
    pause
    exit /b 1
)

set "ALVO=%CD%\Jarvis.exe"
set "ATALHO=%USERPROFILE%\Desktop\Jarvis.lnk"

powershell -NoProfile -Command ^
    "$ws = New-Object -ComObject WScript.Shell;" ^
    "$sc = $ws.CreateShortcut('%ATALHO%');" ^
    "$sc.TargetPath = '%ALVO%';" ^
    "$sc.WorkingDirectory = '%CD%';" ^
    "$sc.IconLocation = '%ALVO%';" ^
    "$sc.Save()"

if exist "%ATALHO%" (
    echo.
    echo Atalho criado na Area de Trabalho: Jarvis
) else (
    echo.
    echo [ERRO] Nao consegui criar o atalho. Tente arrastar o Jarvis.exe
    echo        manualmente para a Area de Trabalho segurando a tecla Alt.
)
echo.
pause
