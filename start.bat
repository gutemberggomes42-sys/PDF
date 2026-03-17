@echo off
echo Iniciando PDF para Audio Converter...
echo.
echo Verificando instalacao do Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo Erro: Python nao encontrado. Por favor, instale o Python 3.7 ou superior.
    pause
    exit /b 1
)

echo Python encontrado!
echo.
echo Instalando dependencias...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo Erro ao instalar dependencias. Verifique sua conexao com a internet.
    pause
    exit /b 1
)

echo Dependencias instaladas com sucesso!
echo.
echo Iniciando aplicativo...
echo.
echo O aplicativo estara disponivel em: http://localhost:5000
echo Pressione Ctrl+C para parar o servidor.
echo.
python app.py
