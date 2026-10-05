@echo off
REM ============================================================
REM  Jarvis - gera o Jarvis.exe (ETAPA EXE-2)
REM
REM  Rode este arquivo DENTRO da pasta do projeto, com o venv ja
REM  ativado (o mesmo venv de sempre, onde "python main.py --text"
REM  ja funciona). So funciona no Windows - o .exe gerado e so pra
REM  Windows mesmo.
REM ============================================================

if not exist "main.py" (
    echo [ERRO] Rode este arquivo de dentro da pasta do projeto Jarvis ^(onde esta o main.py^).
    pause
    exit /b 1
)

echo.
echo === Verificando/instalando o PyInstaller ===
python -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    python -m pip install pyinstaller
    if errorlevel 1 (
        echo [ERRO] Nao consegui instalar o pyinstaller. Confira sua internet/venv.
        pause
        exit /b 1
    )
)

echo.
echo === Gerando o Jarvis.exe ^(pode demorar alguns minutos^) ===
python -m PyInstaller jarvis.spec --noconfirm

if not exist "dist\Jarvis.exe" (
    echo.
    echo [ERRO] O Jarvis.exe nao foi gerado. Veja as mensagens de erro acima.
    pause
    exit /b 1
)

echo.
echo === Copiando arquivos de apoio para perto do .exe ===
if not exist "dist\.env.example" copy ".env.example" "dist\.env.example" >nul
if not exist "dist\config" mkdir "dist\config"
if exist "config\apps.json" copy "config\apps.json" "dist\config\apps.json" >nul

echo.
echo ============================================================
echo   Pronto! O Jarvis.exe esta em: dist\Jarvis.exe
echo.
echo   Pode mover essa pasta "dist" inteira pra onde quiser (Area
echo   de Trabalho, por exemplo) - so nao separe o .exe do arquivo
echo   .env.example/pasta config que estao do lado dele.
echo.
echo   Na primeira vez que abrir o Jarvis.exe, a tela "Configurar IA"
echo   abre sozinha, sem precisar editar nada na mao.
echo ============================================================
echo.
pause
