import os
import time
import hashlib
import json
import asyncio
import concurrent.futures
from multiprocessing import Pool, cpu_count
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import numpy as np
from scipy import signal
import librosa
import pydub
from pydub import AudioSegment
import speech_recognition as sr
import nltk
from textblob import TextBlob
from langdetect import detect
import spacy
from transformers import pipeline, AutoModelForSequenceClassification, AutoTokenizer
import torch
import cv2
import easyocr
import pytesseract
from PIL import Image
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.graph_objects as go
import plotly.express as px
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
from sklearn.metrics.pairwise import cosine_similarity
import redis
import celery
from datetime import datetime
import logging

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AdvancedTextProcessor:
    """Processador avançado de texto com IA e análise"""
    
    def __init__(self):
        self.nlp = None
        self.sentiment_analyzer = None
        self.summarizer = None
        self.ocr_reader = None
        self.load_models()
    
    def load_models(self):
        """Carrega modelos de IA"""
        try:
            # Carregar modelo spaCy para português
            self.nlp = spacy.load("pt_core_news_sm")
        except OSError:
            logger.warning("Modelo spaCy português não encontrado, usando inglês")
            try:
                self.nlp = spacy.load("en_core_web_sm")
            except OSError:
                logger.error("Nenhum modelo spaCy disponível")
                self.nlp = None
        
        # Carregar analisador de sentimento
        try:
            self.sentiment_analyzer = pipeline(
                "sentiment-analysis",
                model="cardiffnlp/twitter-roberta-base-sentiment-latest"
            )
        except Exception as e:
            logger.warning(f"Erro ao carregar analisador de sentimento: {e}")
            self.sentiment_analyzer = None
        
        # Carregar resumidor
        try:
            self.summarizer = pipeline(
                "summarization",
                model="facebook/bart-large-cnn"
            )
        except Exception as e:
            logger.warning(f"Erro ao carregar resumidor: {e}")
            self.summarizer = None
        
        # Carregar OCR
        try:
            self.ocr_reader = easyocr.Reader(['pt', 'en'])
        except Exception as e:
            logger.warning(f"Erro ao carregar OCR: {e}")
            self.ocr_reader = None
    
    def detect_language(self, text):
        """Detecta idioma do texto"""
        try:
            return detect(text)
        except:
            return 'pt'  # Default para português
    
    def analyze_sentiment(self, text):
        """Analisa sentimento do texto"""
        if self.sentiment_analyzer:
            try:
                result = self.sentiment_analyzer(text[:512])  # Limitar tamanho
                return result[0]
            except Exception as e:
                logger.error(f"Erro na análise de sentimento: {e}")
        
        # Fallback com TextBlob
        try:
            blob = TextBlob(text)
            polarity = blob.sentiment.polarity
            if polarity > 0.1:
                return {'label': 'POSITIVE', 'score': polarity}
            elif polarity < -0.1:
                return {'label': 'NEGATIVE', 'score': abs(polarity)}
            else:
                return {'label': 'NEUTRAL', 'score': 0.0}
        except:
            return {'label': 'NEUTRAL', 'score': 0.0}
    
    def extract_entities(self, text):
        """Extrai entidades nomeadas"""
        if self.nlp:
            doc = self.nlp(text)
            entities = []
            for ent in doc.ents:
                entities.append({
                    'text': ent.text,
                    'label': ent.label_,
                    'start': ent.start_char,
                    'end': ent.end_char
                })
            return entities
        return []
    
    def summarize_text(self, text, max_length=150):
        """Resume o texto"""
        if self.summarizer and len(text) > 100:
            try:
                result = self.summarizer(
                    text,
                    max_length=max_length,
                    min_length=50,
                    do_sample=False
                )
                return result[0]['summary_text']
            except Exception as e:
                logger.error(f"Erro no resumo: {e}")
        
        # Fallback - extrair primeiras frases
        sentences = text.split('.')[:3]
        return '. '.join(sentences) + '.'
    
    def extract_keywords(self, text, num_keywords=10):
        """Extrai palavras-chave usando TF-IDF"""
        try:
            # Preparar texto
            documents = [text]
            vectorizer = TfidfVectorizer(
                max_features=num_keywords,
                stop_words=None,
                ngram_range=(1, 2)
            )
            
            tfidf_matrix = vectorizer.fit_transform(documents)
            feature_names = vectorizer.get_feature_names_out()
            tfidf_scores = tfidf_matrix.toarray()[0]
            
            # Ordenar por score
            keyword_scores = list(zip(feature_names, tfidf_scores))
            keyword_scores.sort(key=lambda x: x[1], reverse=True)
            
            return keyword_scores[:num_keywords]
        except Exception as e:
            logger.error(f"Erro na extração de palavras-chave: {e}")
            return []
    
    def advanced_ocr(self, image_path):
        """OCR avançado com múltiplos métodos"""
        results = []
        
        # Método 1: EasyOCR
        if self.ocr_reader:
            try:
                result = self.ocr_reader.readtext(image_path)
                easy_text = ' '.join([item[1] for item in result])
                confidence = np.mean([item[2] for item in result]) if result else 0
                results.append({
                    'method': 'EasyOCR',
                    'text': easy_text,
                    'confidence': confidence
                })
            except Exception as e:
                logger.error(f"Erro no EasyOCR: {e}")
        
        # Método 2: Tesseract
        try:
            image = Image.open(image_path)
            tesseract_text = pytesseract.image_to_string(image, lang='por+eng')
            results.append({
                'method': 'Tesseract',
                'text': tesseract_text,
                'confidence': 0.8  # Tesseract não fornece confiança facilmente
            })
        except Exception as e:
            logger.error(f"Erro no Tesseract: {e}")
        
        # Método 3: PaddleOCR (se disponível)
        try:
            from paddleocr import PaddleOCR
            paddle_ocr = PaddleOCR(use_angle_cls=True, lang='pt')
            result = paddle_ocr.ocr(image_path, cls=True)
            paddle_text = ' '.join([item[1][0] for line in result for item in line])
            results.append({
                'method': 'PaddleOCR',
                'text': paddle_text,
                'confidence': 0.85
            })
        except Exception as e:
            logger.warning(f"PaddleOCR não disponível: {e}")
        
        # Retornar o melhor resultado
        if results:
            best_result = max(results, key=lambda x: x['confidence'])
            return best_result
        
        return {'method': 'None', 'text': '', 'confidence': 0.0}

class ParallelAudioProcessor:
    """Processador de áudio paralelo com otimizações"""
    
    def __init__(self, max_workers=None):
        self.max_workers = max_workers or cpu_count()
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        
    def process_page_parallel(self, pages_data, options):
        """Processa múltiplas páginas em paralelo"""
        futures = []
        
        for i, page_data in enumerate(pages_data):
            future = self.executor.submit(
                self._process_single_page,
                page_data,
                options,
                i
            )
            futures.append(future)
        
        results = []
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result(timeout=300)  # 5 minutos timeout
                results.append(result)
            except Exception as e:
                logger.error(f"Erro no processamento paralelo: {e}")
        
        # Ordenar resultados por número da página
        results.sort(key=lambda x: x['page_number'])
        return results
    
    def _process_single_page(self, page_data, options, index):
        """Processa uma única página com otimizações"""
        page_number = page_data['page_number']
        text = page_data['text']
        
        try:
            # Pré-processamento do texto
            cleaned_text = self._preprocess_text(text, options)
            
            # Dividir em chunks otimizados
            chunks = self._optimize_chunks(cleaned_text, options)
            
            # Processar chunks
            audio_files = []
            for j, chunk in enumerate(chunks):
                audio_file = self._convert_chunk_to_audio(
                    chunk,
                    page_number,
                    j,
                    options
                )
                if audio_file:
                    audio_files.append(audio_file)
            
            # Pós-processamento e otimização
            if len(audio_files) > 1:
                merged_file = self._merge_audio_files(audio_files, page_number, options)
                return {
                    'page_number': page_number,
                    'audio_files': [merged_file],
                    'chunks_processed': len(chunks),
                    'processing_time': time.time()
                }
            elif audio_files:
                return {
                    'page_number': page_number,
                    'audio_files': audio_files,
                    'chunks_processed': len(chunks),
                    'processing_time': time.time()
                }
            
        except Exception as e:
            logger.error(f"Erro ao processar página {page_number}: {e}")
        
        return {
            'page_number': page_number,
            'audio_files': [],
            'error': str(e),
            'processing_time': time.time()
        }
    
    def _preprocess_text(self, text, options):
        """Pré-processamento avançado de texto"""
        # Limpeza básica
        text = text.strip()
        
        # Remover caracteres problemáticos
        import re
        text = re.sub(r'[^\w\s\.\,\!\?\;\:\-\n\r\'\"]', '', text)
        
        # Normalizar espaços
        text = re.sub(r'\s+', ' ', text)
        
        # Dividir sentenças longas
        if options.get('split_long_sentences', True):
            sentences = text.split('. ')
            processed_sentences = []
            for sentence in sentences:
                if len(sentence) > 200:
                    # Dividir sentença longa
                    words = sentence.split()
                    chunks = [' '.join(words[i:i+30]) for i in range(0, len(words), 30)]
                    processed_sentences.extend(chunks)
                else:
                    processed_sentences.append(sentence)
            text = '. '.join(processed_sentences)
        
        return text
    
    def _optimize_chunks(self, text, options):
        """Otimiza divisão do texto em chunks"""
        max_chars = options.get('max_chars', 1000)
        
        # Tentar divisão inteligente em sentenças
        sentences = text.split('. ')
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            if len(current_chunk + sentence) <= max_chars:
                current_chunk += sentence + '. '
            else:
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                current_chunk = sentence + '. '
        
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        # Se chunks muito grandes, dividir por caracteres
        if any(len(chunk) > max_chars for chunk in chunks):
            chunks = self._force_char_chunks(text, max_chars)
        
        return chunks
    
    def _force_char_chunks(self, text, max_chars):
        """Força divisão por caracteres"""
        return [text[i:i+max_chars] for i in range(0, len(text), max_chars)]
    
    def _convert_chunk_to_audio(self, chunk, page_number, chunk_index, options):
        """Converte chunk para áudio com otimizações"""
        try:
            from gtts import gTTS
            
            lang = options.get('lang', 'pt')
            speed = options.get('speed', 1.0)
            
            # Ajustar velocidade
            slow = speed < 0.8
            
            tts = gTTS(text=chunk, lang=lang, slow=slow)
            
            # Nome do arquivo otimizado
            filename = f"page_{page_number:03d}_chunk_{chunk_index:02d}.mp3"
            filepath = os.path.join('audio', filename)
            
            # Garantir que o diretório existe
            os.makedirs('audio', exist_ok=True)
            
            tts.save(filepath)
            
            # Pós-processamento de áudio
            if options.get('enhance_audio', True):
                self._enhance_audio_file(filepath, options)
            
            return filepath
            
        except Exception as e:
            logger.error(f"Erro na conversão do chunk: {e}")
            return None
    
    def _enhance_audio_file(self, filepath, options):
        """Aplica melhorias ao arquivo de áudio"""
        try:
            audio = AudioSegment.from_mp3(filepath)
            
            # Normalização de volume
            if options.get('normalize_volume', True):
                audio = self._normalize_audio(audio)
            
            # Redução de ruído
            if options.get('reduce_noise', True):
                audio = self._reduce_noise(audio)
            
            # Ajuste de pitch
            if options.get('pitch_shift', 1.0) != 1.0:
                audio = self._shift_pitch(audio, options['pitch_shift'])
            
            # Salvar arquivo melhorado
            audio.export(filepath, format="mp3", bitrate="192k")
            
        except Exception as e:
            logger.error(f"Erro na melhoria do áudio: {e}")
    
    def _normalize_audio(self, audio):
        """Normaliza o volume do áudio"""
        change_in_dBFS = -audio.dBFS
        return audio.apply_gain(change_in_dBFS)
    
    def _reduce_noise(self, audio):
        """Reduz ruído do áudio (implementação simplificada)"""
        # Implementação básica - em produção usar bibliotecas especializadas
        return audio.high_pass_filter(80).low_pass_filter(8000)
    
    def _shift_pitch(self, audio, semitones):
        """Altera o pitch do áudio"""
        # Implementação simplificada
        new_sample_rate = int(audio.frame_rate * (2 ** (semitones / 12)))
        return audio._spawn(audio.raw_data, overrides={
            "frame_rate": new_sample_rate
        }).set_frame_rate(audio.frame_rate)
    
    def _merge_audio_files(self, audio_files, page_number, options):
        """Mescla múltiplos arquivos de áudio"""
        try:
            combined = AudioSegment.empty()
            for audio_file in audio_files:
                audio = AudioSegment.from_mp3(audio_file)
                combined += audio
            
            # Adicionar pequena pausa entre chunks
            if options.get('add_pause', True):
                pause = AudioSegment.silent(duration=500)  # 500ms
                combined = combined + pause
            
            # Salvar arquivo mesclado
            merged_filename = f"page_{page_number:03d}_merged.mp3"
            merged_filepath = os.path.join('audio', merged_filename)
            
            combined.export(merged_filepath, format="mp3", bitrate="192k")
            
            # Remover arquivos temporários
            for audio_file in audio_files:
                try:
                    os.remove(audio_file)
                except:
                    pass
            
            return merged_filepath
            
        except Exception as e:
            logger.error(f"Erro ao mesclar áudios: {e}")
            return audio_files[0] if audio_files else None

class AnalyticsEngine:
    """Motor de análise e estatísticas"""
    
    def __init__(self):
        self.vectorizer = TfidfVectorizer(max_features=1000)
        self.kmeans = KMeans(n_clusters=5, random_state=42)
    
    def generate_document_stats(self, text):
        """Gera estatísticas completas do documento"""
        stats = {}
        
        # Estatísticas básicas
        words = text.split()
        stats['word_count'] = len(words)
        stats['char_count'] = len(text)
        stats['char_count_no_spaces'] = len(text.replace(' ', ''))
        stats['sentence_count'] = len(text.split('.'))
        stats['paragraph_count'] = len(text.split('\n\n'))
        
        # Estatísticas avançadas
        stats['avg_word_length'] = np.mean([len(word) for word in words]) if words else 0
        stats['avg_sentence_length'] = np.mean([len(sent.split()) for sent in text.split('.')]) if text.split('.') else 0
        
        # Tempo de leitura
        words_per_minute = 200
        stats['reading_time_minutes'] = stats['word_count'] / words_per_minute
        stats['reading_time_formatted'] = self._format_time(stats['reading_time_minutes'])
        
        # Análise de complexidade
        stats['flesch_kincaid'] = self._calculate_flesch_kincaid(text)
        stats['complexity_level'] = self._get_complexity_level(stats['flesch_kincaid'])
        
        return stats
    
    def _format_time(self, minutes):
        """Formata tempo em minutos e horas"""
        if minutes < 60:
            return f"{int(minutes)} min"
        else:
            hours = int(minutes // 60)
            mins = int(minutes % 60)
            return f"{hours}h {mins}min"
    
    def _calculate_flesch_kincaid(self, text):
        """Calcula índice Flesch-Kincaid"""
        sentences = text.split('.')
        words = text.split()
        
        if not sentences or not words:
            return 0
        
        avg_sentence_length = len(words) / len(sentences)
        avg_syllables = np.mean([self._count_syllables(word) for word in words])
        
        # Fórmula Flesch-Kincaid
        score = 206.835 - 1.015 * avg_sentence_length - 84.6 * avg_syllables
        return max(0, min(100, score))
    
    def _count_syllables(self, word):
        """Conta sílabas em uma palavra (implementação simplificada)"""
        word = word.lower()
        vowels = "aeiouy"
        syllable_count = 0
        prev_char_was_vowel = False
        
        for char in word:
            is_vowel = char in vowels
            if is_vowel and not prev_char_was_vowel:
                syllable_count += 1
            prev_char_was_vowel = is_vowel
        
        if word.endswith("e"):
            syllable_count -= 1
        
        return max(1, syllable_count)
    
    def _get_complexity_level(self, score):
        """Classifica o nível de complexidade"""
        if score >= 90:
            return "Muito Fácil"
        elif score >= 80:
            return "Fácil"
        elif score >= 70:
            return "Relativamente Fácil"
        elif score >= 60:
            return "Padrão"
        elif score >= 50:
            return "Relativamente Difícil"
        elif score >= 30:
            return "Difícil"
        else:
            return "Muito Difícil"
    
    def generate_word_cloud_data(self, text, max_words=50):
        """Gera dados para nuvem de palavras"""
        words = text.lower().split()
        word_freq = {}
        
        # Remover stop words básicas
        stop_words = {'o', 'a', 'os', 'as', 'de', 'do', 'da', 'dos', 'das', 'em', 'no', 'na', 'nos', 'nas', 'por', 'para', 'com', 'sem', 'sob', 'sobre'}
        
        for word in words:
            word = word.strip('.,!?;:"()[]{}')
            if len(word) > 3 and word not in stop_words:
                word_freq[word] = word_freq.get(word, 0) + 1
        
        # Ordenar por frequência
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        
        return sorted_words[:max_words]
    
    def analyze_document_structure(self, text):
        """Analisa a estrutura do documento"""
        structure = {}
        
        # Detectar capítulos
        lines = text.split('\n')
        potential_chapters = []
        
        for i, line in enumerate(lines):
            line = line.strip()
            if line and (line.startswith('Capítulo') or line.startswith('Chapter') or 
                        (len(line) < 50 and line[0].isupper() and line.endswith('.'))):
                potential_chapters.append({
                    'line_number': i,
                    'content': line,
                    'type': 'chapter'
                })
        
        structure['chapters'] = potential_chapters
        
        # Detectar títulos
        headers = []
        for i, line in enumerate(lines):
            line = line.strip()
            if line and ((line.startswith('#') and len(line) < 100) or 
                        (len(line) < 50 and line[0].isupper() and not line.endswith('.'))):
                headers.append({
                    'line_number': i,
                    'content': line,
                    'type': 'header'
                })
        
        structure['headers'] = headers
        
        return structure
    
    def create_readability_chart(self, text):
        """Cria gráfico de legibilidade"""
        stats = self.generate_document_stats(text)
        
        fig = go.Figure()
        
        # Gráfico de barras para métricas
        metrics = ['Palavras', 'Caracteres', 'Sentenças', 'Parágrafos']
        values = [
            stats['word_count'],
            stats['char_count'],
            stats['sentence_count'],
            stats['paragraph_count']
        ]
        
        fig.add_trace(go.Bar(
            x=metrics,
            y=values,
            marker_color='rgb(55, 83, 109)'
        ))
        
        fig.update_layout(
            title='Estatísticas do Documento',
            xaxis_title='Métrica',
            yaxis_title='Quantidade',
            template='plotly_white'
        )
        
        return fig.to_html(include_plotlyjs='cdn')

# Instâncias globais
text_processor = AdvancedTextProcessor()
audio_processor = ParallelAudioProcessor()
analytics_engine = AnalyticsEngine()

# Funções de conveniência
def process_document_advanced(text, options):
    """Processa documento com todas as funcionalidades avançadas"""
    results = {}
    
    # Análise de texto
    results['language'] = text_processor.detect_language(text)
    results['sentiment'] = text_processor.analyze_sentiment(text)
    results['entities'] = text_processor.extract_entities(text)
    results['summary'] = text_processor.summarize_text(text)
    results['keywords'] = text_processor.extract_keywords(text)
    
    # Estatísticas
    results['stats'] = analytics_engine.generate_document_stats(text)
    results['structure'] = analytics_engine.analyze_document_structure(text)
    results['word_cloud_data'] = analytics_engine.generate_word_cloud_data(text)
    results['readability_chart'] = analytics_engine.create_readability_chart(text)
    
    return results

def process_images_ocr(image_paths):
    """Processa múltiplas imagens com OCR em paralelo"""
    results = []
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = []
        for image_path in image_paths:
            future = executor.submit(text_processor.advanced_ocr, image_path)
            futures.append(future)
        
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                logger.error(f"Erro no OCR: {e}")
    
    return results
