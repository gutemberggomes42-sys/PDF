#!/bin/bash

echo "Iniciando PDF para Audio Converter..."
echo

echo "Verificando instalacao do Python..."
if ! command -v python3 &> /dev/null; then
    echo "Erro: Python3 nao encontrado. Por favor, instale o Python 3.7 ou superior."
    exit 1
fi

echo "Python encontrado!"
echo

echo "Instalando dependencias..."
if ! pip3 install -r requirements.txt; then
    echo "Erro ao instalar dependencias. Verifique sua conexao com a internet."
    exit 1
fi

echo "Dependencias instaladas com sucesso!"
echo

echo "Iniciando aplicativo..."
echo
echo "O aplicativo estara disponivel em: http://localhost:5000"
echo "Pressione Ctrl+C para parar o servidor."
echo

python3 app.py
