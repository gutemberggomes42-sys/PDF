# PDF para Áudio - Transforme livros em audiolivros

Um aplicativo web completo e avançado que transforma arquivos PDF, DOCX e TXT em arquivos de áudio, permitindo que você ouça seus livros favoritos em qualquer lugar.

## 🚀 Funcionalidades Implementadas

### **📁 Suporte a Múltiplos Formatos**
- ✅ **PDF** - Extração de texto página por página
- ✅ **DOCX** - Suporte completo para documentos Word
- ✅ **TXT** - Arquivos de texto simples
- ✅ **Drag & Drop** - Interface intuitiva de upload

### **🌍 Múltiplos Idiomas**
- ✅ Português (Brasil)
- ✅ English (Inglês)
- ✅ Español (Espanhol)
- ✅ Français (Francês)
- ✅ Deutsch (Alemão)
- ✅ Italiano (Italiano)
- ✅ Русский (Russo)
- ✅ 日本語 (Japonês)
- ✅ 中文 (Chinês)

### **⚙️ Controles Avançados**
- ✅ **Velocidade da Fala** - 0.5x a 2.0x
- ✅ **Tipos de Voz** - Padrão, Feminina, Masculina
- ✅ **Modo Offline** - Vozes locais do Windows (SAPI)
- ✅ **Cache Inteligente** - Evita reconversões

### **🎵 Player de Áudio Profissional**
- ✅ **Playlist Contínua** - Reprodução sequencial automática
- ✅ **Controles Individuais** - Play/Pause por página
- ✅ **Barra de Progresso** - Visualização do progresso total
- ✅ **Download em Lote** - Todos os arquivos ou individuais

### **✨ Funcionalidades Premium**
- ✅ **Edição de Texto** - Edite o texto antes de converter
- ✅ **Processamento Página por Página** - Cada página como um áudio separado
- ✅ **Progresso em Tempo Real** - Acompanhamento detalhado
- ✅ **Recuperação de Cache** - Conversões instantâneas de arquivos já processados

## 🛠️ Tecnologias Utilizadas

- **Backend**: Flask (Python)
- **Frontend**: HTML5, CSS3, JavaScript, Tailwind CSS
- **Processamento**: PyPDF2, python-docx
- **Síntese de Voz**: gTTS (Google), SAPI (Windows)
- **Cache**: Sistema inteligente com hash MD5
- **Ícones**: Font Awesome

## 📋 Pré-requisitos

- Python 3.7 ou superior
- pip (gerenciador de pacotes Python)
- Conexão com internet (para gTTS)
- Windows (para modo offline SAPI)

## 🚀 Instalação e Execução

### 1. Instale as dependências

```bash
pip install -r requirements.txt
```

### 2. Execute o aplicativo

```bash
python app.py
```

### 3. Acesse o aplicativo

Abra seu navegador e acesse: `http://localhost:5000`

## 📖 Como Usar

### **Modo Rápido (Upload Direto)**
1. **Selecione o arquivo** - PDF, DOCX ou TXT
2. **Configure as opções** - Idioma, velocidade, tipo de voz
3. **Clique em Converter** - Processamento automático
4. **Reproduza ou Baixe** - Player integrado ou download

### **Modo Avançado (Edição de Texto)**
1. **Upload do arquivo** - Extraia o texto primeiro
2. **Edite o texto** - Corrija erros, remova seções
3. **Configure opções** - Idioma, velocidade, voz
4. **Converta** - Processamento do texto editado

### **Modo Offline**
1. **Verifique disponibilidade** - `/offline-status`
2. **Selecione "Modo Offline"** - Usa vozes do Windows
3. **Converta sem internet** - Vozes locais SAPI

## 🎛️ Opções de Configuração

### **Idiomas Suportados**
- `pt` - Português (padrão)
- `en` - English
- `es` - Español
- `fr` - Français
- `de` - Deutsch
- `it` - Italiano
- `ru` - Русский
- `ja` - 日本語
- `zh` - 中文

### **Velocidade da Fala**
- `0.5x` - Muito lento
- `0.8x` - Lento
- `1.0x` - Normal (padrão)
- `1.5x` - Rápido
- `2.0x` - Muito rápido

### **Tipos de Voz**
- `default` - Voz padrão do sistema
- `female` - Voz feminina (quando disponível)
- `male` - Voz masculina (quando disponível)

## 📁 Estrutura do Projeto

```
pdf-audio-converter/
├── app.py                    # Aplicação Flask principal
├── requirements.txt           # Dependências Python
├── templates/
│   └── index.html          # Interface web completa
├── uploads/                 # Pasta temporária para uploads
├── audio/                   # Pasta para arquivos de áudio
├── cache/                   # Cache de conversões
├── start.bat                # Script de inicialização (Windows)
├── start.sh                 # Script de inicialização (Linux/Mac)
├── README.md               # Documentação completa
└── INSTRUCOES_RAPIDAS.txt # Guia rápido
```

## 🔧 Configurações Avançadas

### **Limite de Tamanho de Arquivo**
```python
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB
```

### **Configuração de Cache**
```python
app.config['CACHE_FOLDER'] = 'cache'
```

### **Modo Offline SAPI**
Requer Windows e `pywin32` instalado:
```bash
pip install pywin32
```

## 🐛 Solução de Problemas

### **Problemas Comuns**

1. **"Erro ao extrair texto do PDF"**
   - Verifique se o PDF não está protegido por senha
   - Certifique-se de que o PDF contém texto (não apenas imagens)

2. **"Arquivo muito grande"**
   - O limite é de 50MB. Para arquivos maiores, modifique `MAX_CONTENT_LENGTH`

3. **"Erro na conversão de texto para áudio"**
   - Verifique sua conexão com internet (modo online)
   - Tente usar modo offline (Windows)
   - Reduza a velocidade para 0.8x

4. **"Biblioteca não instalada"**
   - Instale todas as dependências: `pip install -r requirements.txt`

### **Diagnóstico**

**Teste o sistema:**
```bash
# Teste TTS online
curl http://localhost:5000/test-tts

# Verificar status offline
curl http://localhost:5000/offline-status

# Listar idiomas
curl http://localhost:5000/languages
```

## 🚀 Melhorias Futuras

- [ ] Suporte para mais formatos (EPUB, MOBI)
- [ ] OCR avançado para PDFs escaneados
- [ ] Sincronização com nuvem
- [ ] Aplicativo mobile
- [ ] Controle por comandos de voz
- [ ] Legendas sincronizadas
- [ ] Modo de estudo com repetição

## 📄 Licença

Este projeto é open source e disponível sob a [MIT License](LICENSE).

## 🤝 Contribuições

Contribuições são bem-vindas! Sinta-se à vontade para:
- Reportar bugs
- Sugerir melhorias
- Enviar pull requests
- Melhorar a documentação

## 📞 Suporte

Se você encontrar algum problema ou tiver alguma dúvida:
1. Verifique a seção de solução de problemas
2. Teste as rotas de diagnóstico
3. Abra uma issue no repositório do projeto

---

**Desenvolvido com ❤️ para transformar a maneira como você consome livros!**

**Versão 2.0 - Completo com todas as funcionalidades avançadas!**
