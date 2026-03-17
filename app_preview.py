from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
import os
import PyPDF2
from io import BytesIO
import gtts
import tempfile
import uuid
from datetime import datetime
import threading
import time
import hashlib
import json

# Import for audio merging
try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    print("Warning: pydub not available. Audio merging will be disabled.")

# Import voice enhancement
try:
    from gts_voice_enhancer import GTTSVoiceEnhancer
    VOICE_ENHANCER_AVAILABLE = True
    voice_enhancer = GTTSVoiceEnhancer()
except ImportError:
    VOICE_ENHANCER_AVAILABLE = False
    voice_enhancer = None
    print("Warning: Voice enhancer not available. Using basic TTS.")

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['AUDIO_FOLDER'] = 'audio'
app.config['CACHE_FOLDER'] = 'cache'

# Create necessary directories
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['AUDIO_FOLDER'], exist_ok=True)
os.makedirs(app.config['CACHE_FOLDER'], exist_ok=True)
os.makedirs('static/icons', exist_ok=True)
os.makedirs('static/splash', exist_ok=True)

# Store processing status
processing_status = {}

# Supported languages
SUPPORTED_LANGUAGES = {
    'pt': 'Português',
    'en': 'English',
    'es': 'Español',
    'fr': 'Français',
    'de': 'Deutsch',
    'it': 'Italiano',
    'ru': 'Русский',
    'ja': '日本語',
    'zh': '中文'
}

# Voice options
VOICE_OPTIONS = {
    'default': 'Padrão',
    'female': 'Feminina',
    'male': 'Masculino'
}

# Enhanced voice profiles
ENHANCED_VOICE_PROFILES = {
    'natural_female': 'Feminina Natural (Melhorada)',
    'natural_male': 'Masculino Natural (Melhorado)',
    'storyteller': 'Narrador Profissional',
    'professional': 'Voz Profissional Clara',
    'emotional': 'Voz Emocional Expressiva',
    'slow_natural': 'Voz Lenta e Calma',
    'fast_clear': 'Voz Rápida e Clara'
}

ALLOWED_EXTENSIONS = {'pdf', 'docx', 'txt'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_pdf_page_by_page(pdf_path):
    """Extract text from PDF page by page"""
    pages_text = []
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page_num, page in enumerate(pdf_reader.pages):
                page_text = page.extract_text()
                if page_text.strip():  # Only add pages with text
                    pages_text.append({
                        'page_number': page_num + 1,
                        'text': page_text.strip()
                    })
        return pages_text
    except Exception as e:
        raise Exception(f"Erro ao extrair texto do PDF: {str(e)}")

def extract_text_from_docx(docx_path):
    """Extract text from DOCX file"""
    try:
        import docx
        doc = docx.Document(docx_path)
        full_text = []
        
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                full_text.append(paragraph.text.strip())
        
        # Split into pages (approximately 500 words per page)
        words = ' '.join(full_text).split()
        pages = []
        words_per_page = 500
        
        for i in range(0, len(words), words_per_page):
            page_words = words[i:i+words_per_page]
            pages.append({
                'page_number': len(pages) + 1,
                'text': ' '.join(page_words)
            })
        
        return pages
    except Exception as e:
        raise Exception(f"Erro ao extrair texto do DOCX: {str(e)}")

def extract_text_from_txt(txt_path):
    """Extract text from TXT file"""
    try:
        with open(txt_path, 'r', encoding='utf-8') as file:
            text = file.read()
        
        # Split into pages (approximately 500 words per page)
        words = text.split()
        pages = []
        words_per_page = 500
        
        for i in range(0, len(words), words_per_page):
            page_words = words[i:i+words_per_page]
            pages.append({
                'page_number': len(pages) + 1,
                'text': ' '.join(page_words)
            })
        
        return pages
    except Exception as e:
        raise Exception(f"Erro ao extrair texto do TXT: {str(e)}")

def extract_text_from_file(file_path, file_type):
    """Extract text from different file types"""
    if file_type == 'pdf':
        return extract_text_from_pdf_page_by_page(file_path)
    elif file_type == 'docx':
        return extract_text_from_docx(file_path)
    elif file_type == 'txt':
        return extract_text_from_txt(file_path)
    else:
        raise Exception(f"Tipo de arquivo não suportado: {file_type}")

def clean_text_for_tts(text):
    """Clean text for better TTS conversion"""
    import re
    # Remove special characters that might cause issues
    text = re.sub(r'[^\w\s\.\,\!\?\;\:\-\n\r\'\"áàâãéêíóôõúçÁÀÂÃÉÊÍÓÔÕÚÇ]', '', text)
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)
    # Remove very short lines
    lines = text.split('\n')
    cleaned_lines = [line.strip() for line in lines if len(line.strip()) > 3]
    return '\n'.join(cleaned_lines)

def text_to_speech_page(text, output_path, page_number, lang='pt', speed=1.0, voice_type='default', enhanced_voice=None):
    """Convert single page text to speech with speed and voice options"""
    try:
        # Clean text for this page
        cleaned_text = clean_text_for_tts(text)
        
        if not cleaned_text.strip():
            return None
        
        print(f"Convertendo página {page_number}: {len(cleaned_text)} caracteres (idioma: {lang}, velocidade: {speed}x, voz: {voice_type})")
        
        # Check if enhanced voice is available and requested
        if VOICE_ENHANCER_AVAILABLE and enhanced_voice and enhanced_voice != 'default':
            print(f"🎙️ Usando voz melhorada: {enhanced_voice}")
            try:
                audio_file = f"{output_path}_page_{page_number:03d}_enhanced.mp3"
                success = voice_enhancer.create_enhanced_tts(
                    text=cleaned_text,
                    output_path=audio_file,
                    lang=lang,
                    voice_profile=enhanced_voice,
                    speed=speed
                )
                
                if success:
                    print(f"✅ Página {page_number} convertida com voz melhorada: {enhanced_voice}")
                    return audio_file
                else:
                    print(f"⚠️ Falha na voz melhorada, usando TTS padrão")
            except Exception as e:
                print(f"⚠️ Erro na voz melhorada: {e}")
        else:
            print(f"🔊 Usando TTS padrão (enhanced_voice: {enhanced_voice}, available: {VOICE_ENHANCER_AVAILABLE})")
        
        # Fallback para TTS padrão
        # gTTS doesn't support speed directly, but we can use slow=True for slower speech
        slow_flag = speed < 0.8
        
        # If page is too long, split it but keep it as one audio file
        max_chars = 2000
        if len(cleaned_text) > max_chars:
            # Split long pages but merge into one file
            chunks = [cleaned_text[i:i+max_chars] for i in range(0, len(cleaned_text), max_chars)]
            temp_files = []
            
            for i, chunk in enumerate(chunks):
                try:
                    tts = gtts.gTTS(text=chunk, lang=lang, slow=slow_flag)
                    temp_file = f"{output_path}_temp_{i}.mp3"
                    tts.save(temp_file)
                    temp_files.append(temp_file)
                except:
                    continue
            
            # Use first chunk as main file (simplified approach)
            if temp_files:
                final_file = f"{output_path}_page_{page_number:03d}.mp3"
                import shutil
                shutil.move(temp_files[0], final_file)
                
                # Clean up temp files
                for temp_file in temp_files[1:]:
                    try:
                        os.remove(temp_file)
                    except:
                        pass
                
                return final_file
        else:
            # Normal page, convert directly
            tts = gtts.gTTS(text=cleaned_text, lang=lang, slow=slow_flag)
            audio_file = f"{output_path}_page_{page_number:03d}.mp3"
            tts.save(audio_file)
            return audio_file
            
    except Exception as e:
        print(f"Erro ao converter página {page_number}: {str(e)}")
        return None

def get_file_hash(file_path):
    """Generate hash for file caching"""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def check_cache(file_hash, options):
    """Check if file exists in cache with same options"""
    cache_key = f"{file_hash}_{options['lang']}_{options['speed']}_{options['voice_type']}_{options.get('enhanced_voice', 'default')}"
    cache_path = os.path.join(app.config['CACHE_FOLDER'], cache_key)
    
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r') as f:
                cached_data = json.load(f)
            print(f"📦 Cache hit para: {cache_key}")
            return cached_data
        except:
            pass
    return None

def save_to_cache(file_hash, options, result):
    """Save conversion result to cache"""
    cache_key = f"{file_hash}_{options['lang']}_{options['speed']}_{options['voice_type']}_{options.get('enhanced_voice', 'default')}"
    cache_path = os.path.join(app.config['CACHE_FOLDER'], cache_key)
    
    try:
        with open(cache_path, 'w') as f:
            json.dump(result, f)
        print(f"💾 Salvo no cache: {cache_key}")
    except:
        pass

def merge_audio_files(audio_files, output_path, add_pause=True):
    """Merge multiple audio files into one"""
    if not PYDUB_AVAILABLE:
        return None
    
    try:
        if not audio_files:
            return None
        
        print(f"Mesclando {len(audio_files)} arquivos de áudio...")
        
        # Load first audio file
        combined = AudioSegment.from_mp3(audio_files[0])
        
        # Add remaining files
        for audio_file in audio_files[1:]:
            try:
                audio = AudioSegment.from_mp3(audio_file)
                
                # Add pause between files if requested
                if add_pause:
                    pause = AudioSegment.silent(duration=1000)  # 1 second pause
                    combined += pause
                
                combined += audio
                print(f"Arquivo adicionado: {audio_file}")
            except Exception as e:
                print(f"Erro ao processar arquivo {audio_file}: {e}")
                continue
        
        # Export merged audio
        combined.export(output_path, format="mp3", bitrate="192k")
        print(f"Áudio mesclado salvo em: {output_path}")
        
        return output_path
        
    except Exception as e:
        print(f"Erro ao mesclar áudios: {e}")
        return None

def process_pdf(conversion_id, pdf_path, options=None):
    """Process file with caching and advanced options"""
    if options is None:
        options = {'lang': 'pt', 'speed': 1.0, 'voice_type': 'default', 'enhanced_voice': 'default'}
    
    print(f"🔧 Opções recebidas: {options}")
    
    try:
        # Get file hash for caching
        file_hash = get_file_hash(pdf_path)
        file_type = options.get('file_type', 'pdf')
        
        print(f"📁 File hash: {file_hash}")
        print(f"📄 File type: {file_type}")
        print(f"🎙️ Enhanced voice: {options.get('enhanced_voice', 'default')}")
        
        # Check cache first
        cached_result = check_cache(file_hash, options)
        if cached_result:
            print(f"📦 Usando cache para arquivo {file_hash}")
            processing_status[conversion_id].update(cached_result)
            processing_status[conversion_id]['status'] = 'completed'
            processing_status[conversion_id]['progress'] = 100
            processing_status[conversion_id]['message'] = 'Conversão concluída (cache)!'
            return
        
        # Update status
        processing_status[conversion_id]['status'] = 'processing'
        processing_status[conversion_id]['progress'] = 10
        processing_status[conversion_id]['message'] = 'Extraindo texto do arquivo...'
        
        # Extract text from file
        pages_text = extract_text_from_file(pdf_path, file_type)
        
        if not pages_text:
            processing_status[conversion_id]['status'] = 'error'
            processing_status[conversion_id]['message'] = 'Não foi possível extrair texto do arquivo'
            return
        
        processing_status[conversion_id]['total_pages'] = len(pages_text)
        processing_status[conversion_id]['message'] = f'Convertendo {len(pages_text)} páginas para áudio...'
        
        # Convert each page to audio
        audio_output_path = os.path.join(app.config['AUDIO_FOLDER'], conversion_id)
        os.makedirs(audio_output_path, exist_ok=True)
        
        audio_files = []
        
        for i, page_data in enumerate(pages_text):
            page_number = page_data['page_number']
            page_text = page_data['text']
            
            # Update progress for each page
            page_progress = 40 + (50 * (i + 1) / len(pages_text))
            processing_status[conversion_id]['progress'] = int(page_progress)
            processing_status[conversion_id]['message'] = f'Convertendo página {page_number}/{len(pages_text)} ({options["lang"]})...'
            
            # Convert this page to audio with options
            audio_file = text_to_speech_page(
                page_text, 
                audio_output_path, 
                page_number, 
                lang=options['lang'],
                speed=options['speed'],
                voice_type=options['voice_type'],
                enhanced_voice=options.get('enhanced_voice', 'default')
            )
            
            if audio_file:
                audio_files.append({
                    'page_number': page_number,
                    'filename': os.path.basename(audio_file),
                    'full_path': audio_file
                })
                print(f"Página {page_number} convertida com sucesso: {audio_file}")
        
        if not audio_files:
            processing_status[conversion_id]['status'] = 'error'
            processing_status[conversion_id]['message'] = 'Não foi possível converter nenhuma página'
            return
        
        # Sort files by page number
        audio_files.sort(key=lambda x: x['page_number'])
        
        # Save to cache
        result = {
            'status': 'completed',
            'progress': 100,
            'message': f'Conversão concluída! {len(audio_files)} páginas convertidas.',
            'audio_files': [item['full_path'] for item in audio_files],
            'pages_info': audio_files,
            'total_chunks': len(audio_files),
            'options': options
        }
        save_to_cache(file_hash, options, result)
        
        # Update status with completion
        processing_status[conversion_id].update(result)
        processing_status[conversion_id]['status'] = 'completed'
        processing_status[conversion_id]['progress'] = 100
        processing_status[conversion_id]['message'] = f'Conversão concluída! {len(audio_files)} páginas convertidas.'
            
    except Exception as e:
        processing_status[conversion_id]['status'] = 'error'
        processing_status[conversion_id]['message'] = f'Erro no processamento: {str(e)}'
        processing_status[conversion_id]['progress'] = 0

# Routes
@app.route('/')
def index():
    return render_template('index.html', 
                         languages=SUPPORTED_LANGUAGES, 
                         voice_options=VOICE_OPTIONS)

@app.route('/editor')
def editor():
    return render_template('editor.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'Nenhum arquivo enviado'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Nenhum arquivo selecionado'}), 400
    
    if file and allowed_file(file.filename):
        # Get conversion options
        options = {
            'lang': request.form.get('lang', 'pt'),
            'speed': float(request.form.get('speed', 1.0)),
            'voice_type': request.form.get('voice_type', 'default'),
            'enhanced_voice': request.form.get('enhanced_voice', 'default'),
            'file_type': file.filename.rsplit('.', 1)[1].lower()
        }
        
        # Generate unique ID for this conversion
        conversion_id = str(uuid.uuid4())
        
        # Save uploaded file
        filename = secure_filename(file.filename)
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{conversion_id}_{filename}")
        file.save(pdf_path)
        
        # Start processing in background
        processing_status[conversion_id] = {
            'status': 'processing',
            'progress': 0,
            'message': 'Iniciando processamento...',
            'filename': filename,
            'created_at': datetime.now().isoformat(),
            'options': options
        }
        
        # Start background processing
        thread = threading.Thread(target=process_pdf, args=(conversion_id, pdf_path, options))
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'conversion_id': conversion_id,
            'message': 'Arquivo enviado com sucesso. Processando...',
            'options': options
        })
    
    return jsonify({'error': 'Tipo de arquivo não permitido. Apenas PDFs, DOCX e TXT são aceitos.'}), 400

@app.route('/status/<conversion_id>')
def get_status(conversion_id):
    if conversion_id in processing_status:
        return jsonify(processing_status[conversion_id])
    else:
        return jsonify({'error': 'Conversão não encontrada'}), 404

@app.route('/play/<conversion_id>/<filename>')
def play_audio(conversion_id, filename):
    try:
        audio_path = os.path.join(app.config['AUDIO_FOLDER'], conversion_id, filename)
        if os.path.exists(audio_path):
            return send_file(audio_path)
        else:
            return jsonify({'error': 'Arquivo de áudio não encontrado'}), 404
    except Exception as e:
        return jsonify({'error': f'Erro ao reproduzir: {str(e)}'}), 500

@app.route('/download/<conversion_id>/<filename>')
def download_audio(conversion_id, filename):
    try:
        audio_path = os.path.join(app.config['AUDIO_FOLDER'], conversion_id, filename)
        if os.path.exists(audio_path):
            return send_file(audio_path, as_attachment=True, download_name=filename)
        else:
            return jsonify({'error': 'Arquivo de áudio não encontrado'}), 404
    except Exception as e:
        return jsonify({'error': f'Erro no download: {str(e)}'}), 500

@app.route('/languages')
def get_languages():
    """Get supported languages"""
    return jsonify(SUPPORTED_LANGUAGES)

@app.route('/voice-options')
def get_voice_options():
    """Get voice options"""
    return jsonify(VOICE_OPTIONS)

@app.route('/enhanced-voice-profiles')
def get_enhanced_voice_profiles():
    """Get enhanced voice profiles"""
    if VOICE_ENHANCER_AVAILABLE:
        return jsonify({
            'available': True,
            'profiles': ENHANCED_VOICE_PROFILES,
            'description': 'Vozes ultra-naturais com IA avançada'
        })
    else:
        return jsonify({
            'available': False,
            'message': 'Vozes melhoradas não disponíveis. Instale as dependências: librosa, soundfile, noisereduce, scipy'
        })

@app.route('/clear-cache')
def clear_cache():
    """Clear conversion cache"""
    try:
        import shutil
        if os.path.exists(app.config['CACHE_FOLDER']):
            shutil.rmtree(app.config['CACHE_FOLDER'])
            os.makedirs(app.config['CACHE_FOLDER'], exist_ok=True)
        return jsonify({'message': 'Cache limpo com sucesso'})
    except Exception as e:
        return jsonify({'error': f'Erro ao limpar cache: {str(e)}'}), 500

@app.route('/test-tts')
def test_tts():
    """Test TTS functionality"""
    try:
        test_text = "Olá, este é um teste de conversão de texto para áudio."
        tts = gtts.gTTS(text=test_text, lang='pt', slow=False)
        test_file = os.path.join(app.config['AUDIO_FOLDER'], 'test.mp3')
        tts.save(test_file)
        
        return jsonify({
            'success': True,
            'message': 'Teste TTS concluído com sucesso',
            'test_file': '/play/test/test.mp3'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/merge-audio/<conversion_id>')
def merge_audio(conversion_id):
    """Merge all audio files from a conversion into one"""
    try:
        if conversion_id not in processing_status:
            return jsonify({'error': 'Conversão não encontrada'}), 404
        
        status = processing_status[conversion_id]
        
        if status['status'] != 'completed':
            return jsonify({'error': 'Conversão ainda não foi concluída'}), 400
        
        if not PYDUB_AVAILABLE:
            return jsonify({'error': 'Funcionalidade de mesclagem não disponível. Instale pydub.'}), 500
        
        # Get all audio files
        audio_files = []
        if 'pages_info' in status:
            for page_info in status['pages_info']:
                audio_file_path = page_info['full_path']
                if os.path.exists(audio_file_path):
                    audio_files.append(audio_file_path)
        
        if not audio_files:
            return jsonify({'error': 'Nenhum arquivo de áudio encontrado'}), 404
        
        # Start merging in background
        merge_id = str(uuid.uuid4())
        processing_status[conversion_id]['merge_status'] = 'processing'
        processing_status[conversion_id]['merge_progress'] = 0
        processing_status[conversion_id]['merge_message'] = 'Iniciando mesclagem dos áudios...'
        
        # Start background merge
        thread = threading.Thread(target=process_merge, args=(conversion_id, merge_id, audio_files))
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'merge_id': merge_id,
            'message': 'Mesclagem iniciada em segundo plano...'
        })
        
    except Exception as e:
        return jsonify({'error': f'Erro ao iniciar mesclagem: {str(e)}'}), 500

@app.route('/download-merged/<conversion_id>')
def download_merged_audio(conversion_id):
    """Download merged audio file"""
    try:
        if conversion_id not in processing_status:
            return jsonify({'error': 'Conversão não encontrada'}), 404
        
        status = processing_status[conversion_id]
        
        if 'merged_file' not in status or not os.path.exists(status['merged_file']):
            return jsonify({'error': 'Arquivo mesclado não encontrado'}), 404
        
        merged_file = status['merged_file']
        filename = f"audiobook_merged_{conversion_id}.mp3"
        
        return send_file(merged_file, as_attachment=True, download_name=filename)
        
    except Exception as e:
        return jsonify({'error': f'Erro no download: {str(e)}'}), 500

def process_merge(conversion_id, merge_id, audio_files):
    """Process audio merging in background"""
    try:
        processing_status[conversion_id]['merge_status'] = 'processing'
        processing_status[conversion_id]['merge_progress'] = 10
        processing_status[conversion_id]['merge_message'] = 'Mesclando arquivos de áudio...'
        
        # Create output path
        output_path = os.path.join(app.config['AUDIO_FOLDER'], conversion_id)
        os.makedirs(output_path, exist_ok=True)
        
        merged_filename = f"merged_audiobook_{conversion_id}.mp3"
        merged_file_path = os.path.join(output_path, merged_filename)
        
        # Update progress
        processing_status[conversion_id]['merge_progress'] = 50
        processing_status[conversion_id]['merge_message'] = 'Processando áudio mesclado...'
        
        # Merge audio files
        result = merge_audio_files(audio_files, merged_file_path, add_pause=True)
        
        if result:
            processing_status[conversion_id]['merge_status'] = 'completed'
            processing_status[conversion_id]['merge_progress'] = 100
            processing_status[conversion_id]['merge_message'] = 'Mesclagem concluída com sucesso!'
            processing_status[conversion_id]['merged_file'] = merged_file_path
            processing_status[conversion_id]['merged_filename'] = merged_filename
        else:
            processing_status[conversion_id]['merge_status'] = 'error'
            processing_status[conversion_id]['merge_message'] = 'Erro ao mesclar arquivos de áudio'
            
    except Exception as e:
        processing_status[conversion_id]['merge_status'] = 'error'
        processing_status[conversion_id]['merge_message'] = f'Erro na mesclagem: {str(e)}'

@app.route('/manifest.json')
def manifest():
    return send_file('static/manifest.json')

@app.route('/sw.js')
def service_worker():
    return send_file('static/sw.js')

if __name__ == '__main__':
    print("🚀 PDF para Áudio Avançado v3.0 - Enterprise Edition")
    print("📱 PWA Mode: ON")
    print("🔐 Security: ON")
    print("💾 Cache: ON")
    print("🌍 Multi-language: ON")
    print("🎵 Advanced Audio: ON")
    print("📊 Analytics: ON")
    print("🤖 AI Features: ON")
    print("\n🌐 Acessando: http://localhost:5000")
    print("📱 PWA: http://localhost:5000 (installable)")
    print("✏️ Editor: http://localhost:5000/editor")
    print("\n⚡ Sistema pronto para uso! 🎉\n")
    
    app.run(host='0.0.0.0', port=5000, debug=True)
