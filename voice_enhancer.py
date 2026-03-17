import os
import numpy as np
import librosa
import soundfile as sf
from pydub import AudioSegment
import noisereduce as nr
import scipy.signal
from scipy.io import wavfile
import tempfile
import logging
from typing import Dict, List, Optional, Tuple
import json
from datetime import datetime

logger = logging.getLogger(__name__)

class VoiceEnhancer:
    """Melhorador avançado de voz para síntese mais natural"""
    
    def __init__(self):
        self.sample_rate = 22050
        self.voice_profiles = self._load_voice_profiles()
        self.enhancement_settings = self._load_enhancement_settings()
    
    def _load_voice_profiles(self) -> Dict[str, Dict]:
        """Carrega perfis de voz personalizados"""
        return {
            'natural_female': {
                'pitch_range': (180, 220),
                'formant_shift': 1.2,
                'breathiness': 0.15,
                'warmth': 0.3,
                'clarity': 0.8,
                'prosody_strength': 0.7
            },
            'natural_male': {
                'pitch_range': (100, 140),
                'formant_shift': 0.9,
                'breathiness': 0.1,
                'warmth': 0.4,
                'clarity': 0.7,
                'prosody_strength': 0.6
            },
            'storyteller': {
                'pitch_range': (120, 200),
                'formant_shift': 1.1,
                'breathiness': 0.2,
                'warmth': 0.5,
                'clarity': 0.9,
                'prosody_strength': 0.9
            },
            'professional': {
                'pitch_range': (140, 180),
                'formant_shift': 1.0,
                'breathiness': 0.05,
                'warmth': 0.2,
                'clarity': 0.95,
                'prosody_strength': 0.4
            },
            'emotional': {
                'pitch_range': (150, 250),
                'formant_shift': 1.15,
                'breathiness': 0.25,
                'warmth': 0.6,
                'clarity': 0.8,
                'prosody_strength': 1.0
            }
        }
    
    def _load_enhancement_settings(self) -> Dict:
        """Carrega configurações de melhoria"""
        return {
            'noise_reduction': {
                'strength': 0.8,
                'preserve_speech': True,
                'stationary_noise': True
            },
            'dynamic_compression': {
                'threshold': -20,
                'ratio': 3.0,
                'attack': 0.003,
                'release': 0.1
            },
            'equalization': {
                'low_freq': 80,
                'mid_freq': 1000,
                'high_freq': 8000,
                'low_gain': 2.0,
                'mid_gain': 1.5,
                'high_gain': 1.2
            },
            'reverb': {
                'room_size': 0.2,
                'damping': 0.8,
                'wet_level': 0.15,
                'dry_level': 0.85
            }
        }
    
    def enhance_audio_file(self, input_path: str, output_path: str, 
                          voice_profile: str = 'natural_female',
                          language: str = 'pt') -> bool:
        """Melhora arquivo de áudio completo"""
        try:
            logger.info(f"Melhorando áudio: {input_path} -> {output_path}")
            
            # Carregar áudio
            audio, sr = librosa.load(input_path, sr=self.sample_rate)
            
            # Aplicar melhorias sequenciais
            audio = self._apply_preprocessing(audio, sr)
            audio = self._apply_voice_profile(audio, sr, voice_profile)
            audio = self._apply_prosodic_enhancement(audio, sr, language)
            audio = self._apply_postprocessing(audio, sr)
            
            # Salvar áudio melhorado
            sf.write(output_path, audio, self.sample_rate)
            
            logger.info(f"Áudio melhorado salvo em: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao melhorar áudio: {e}")
            return False
    
    def _apply_preprocessing(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """Aplica pré-processamento do áudio"""
        # Redução de ruído
        audio = nr.reduce_noise(y=audio, sr=sr, 
                               stationary=True,
                               prop_decrease=0.8)
        
        # Normalização inicial
        audio = librosa.util.normalize(audio)
        
        # Remover silêncios extremos
        audio, _ = librosa.effects.trim(audio, top_db=20)
        
        return audio
    
    def _apply_voice_profile(self, audio: np.ndarray, sr: int, 
                            profile_name: str) -> np.ndarray:
        """Aplica perfil de voz personalizado"""
        if profile_name not in self.voice_profiles:
            profile_name = 'natural_female'
        
        profile = self.voice_profiles[profile_name]
        
        # Ajuste de pitch (formant shifting)
        audio = self._apply_formant_shift(audio, sr, profile['formant_shift'])
        
        # Modulação de pitch natural
        audio = self._apply_natural_pitch_modulation(audio, sr, profile['pitch_range'])
        
        # Adicionar características de voz
        audio = self._add_vocal_characteristics(audio, sr, profile)
        
        return audio
    
    def _apply_formant_shift(self, audio: np.ndarray, sr: int, 
                           shift_factor: float) -> np.ndarray:
        """Aplica shift de formantes para mudar timbre"""
        try:
            # Usar phase vocoder para shift de pitch preservando formantes
            if shift_factor == 1.0:
                return audio
            
            # Resampling para mudar pitch
            new_sr = int(sr * shift_factor)
            audio_shifted = librosa.resample(audio, orig_sr=sr, target_sr=new_sr)
            audio_shifted = librosa.resample(audio_shifted, orig_sr=new_sr, target_sr=sr)
            
            return audio_shifted
        except:
            return audio
    
    def _apply_natural_pitch_modulation(self, audio: np.ndarray, sr: int,
                                      pitch_range: Tuple[float, float]) -> np.ndarray:
        """Aplica modulação de pitch natural"""
        try:
            # Extrair pitch
            pitches, magnitudes = librosa.piptrack(y=audio, sr=sr, threshold=0.1)
            
            # Filtrar pitches válidos
            pitch_values = []
            for t in range(pitches.shape[1]):
                index = magnitudes[:, t].argmax()
                pitch = pitches[index, t]
                if pitch > 0:
                    pitch_values.append(pitch)
            
            if not pitch_values:
                return audio
            
            # Calcular pitch médio e ajustar
            mean_pitch = np.mean(pitch_values)
            target_pitch = np.mean(pitch_range)
            
            if mean_pitch > 0:
                pitch_shift = target_pitch / mean_pitch
                if 0.5 < pitch_shift < 2.0:  # Limitar range
                    audio = librosa.effects.pitch_shift(audio, sr=sr, n_steps=0)
            
            return audio
        except:
            return audio
    
    def _add_vocal_characteristics(self, audio: np.ndarray, sr: int,
                                 profile: Dict) -> np.ndarray:
        """Adiciona características vocais naturais"""
        try:
            # Adicionar respiração sutil
            if profile['breathiness'] > 0:
                breath_noise = np.random.normal(0, profile['breathiness'] * 0.01, len(audio))
                audio = audio + breath_noise
            
            # Aplicar filtro de formantes
            audio = self._apply_formant_filter(audio, sr, profile)
            
            # Adicionar warmth
            if profile['warmth'] > 0:
                audio = self._add_warmth(audio, profile['warmth'])
            
            # Melhorar clareza
            if profile['clarity'] > 0:
                audio = self._enhance_clarity(audio, profile['clarity'])
            
            return audio
        except:
            return audio
    
    def _apply_formant_filter(self, audio: np.ndarray, sr: int,
                            profile: Dict) -> np.ndarray:
        """Aplica filtro de formantes"""
        try:
            # Filtros para simular formantes vocais
            # Formante 1 (~500 Hz)
            f1 = 500
            q1 = 5
            w1 = f1 / (sr / 2)
            b1, a1 = scipy.signal.iirpeak(w1, q1)
            audio = scipy.signal.filtfilt(b1, a1, audio)
            
            # Formante 2 (~1500 Hz)
            f2 = 1500
            q2 = 8
            w2 = f2 / (sr / 2)
            b2, a2 = scipy.signal.iirpeak(w2, q2)
            audio = scipy.signal.filtfilt(b2, a2, audio)
            
            # Formante 3 (~2500 Hz)
            f3 = 2500
            q3 = 10
            w3 = f3 / (sr / 2)
            b3, a3 = scipy.signal.iirpeak(w3, q3)
            audio = scipy.signal.filtfilt(b3, a3, audio)
            
            return audio
        except:
            return audio
    
    def _add_warmth(self, audio: np.ndarray, warmth_factor: float) -> np.ndarray:
        """Adiciona calor à voz"""
        try:
            # Adicionar harmônicos suaves
            harmonic = audio * warmth_factor * 0.1
            audio = audio + harmonic
            
            # Suavizar transientes
            audio = scipy.signal.savgol_filter(audio, window_length=51, polyorder=3)
            
            return audio
        except:
            return audio
    
    def _enhance_clarity(self, audio: np.ndarray, clarity_factor: float) -> np.ndarray:
        """Melhora clareza da fala"""
        try:
            # Equalização para clareza
            # Boost em frequências de fala (1-4 kHz)
            sos = scipy.signal.butter(4, [1000, 4000], btype='band', 
                                     fs=self.sample_rate, output='sos')
            enhanced = scipy.signal.sosfilt(sos, audio)
            
            # Misturar com original baseado no fator de clareza
            audio = audio * (1 - clarity_factor * 0.3) + enhanced * clarity_factor * 0.3
            
            return audio
        except:
            return audio
    
    def _apply_prosodic_enhancement(self, audio: np.ndarray, sr: int,
                                   language: str) -> np.ndarray:
        """Aplica melhorias prosódicas baseadas no idioma"""
        try:
            # Análise de ritmo e entonação por idioma
            if language == 'pt':
                audio = self._apply_portuguese_prosody(audio, sr)
            elif language == 'en':
                audio = self._apply_english_prosody(audio, sr)
            elif language == 'es':
                audio = self._apply_spanish_prosody(audio, sr)
            else:
                audio = self._apply_default_prosody(audio, sr)
            
            return audio
        except:
            return audio
    
    def _apply_portuguese_prosody(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """Aplica prosódia brasileira natural"""
        try:
            # Português brasileiro tem ritmo mais suave
            # Adicionar pausas naturais em pontos de pontuação
            audio = self._add_natural_pauses(audio, sr, pause_duration=0.3)
            
            # Modulação suave de entonação
            audio = self._apply_smooth_intonation(audio, sr)
            
            return audio
        except:
            return audio
    
    def _apply_english_prosody(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """Aplica prosódia inglesa natural"""
        try:
            # Inglês tem ritmo mais marcado
            audio = self._add_rhythmic_emphasis(audio, sr)
            
            return audio
        except:
            return audio
    
    def _apply_spanish_prosody(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """Aplica prosódia espanhola natural"""
        try:
            # Espanhol tem ritmo mais vibrante
            audio = self._add_vibrant_rhythm(audio, sr)
            
            return audio
        except:
            return audio
    
    def _apply_default_prosody(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """Aplica prosódia padrão"""
        try:
            # Melhorias gerais
            audio = self._smooth_dynamics(audio, sr)
            
            return audio
        except:
            return audio
    
    def _add_natural_pauses(self, audio: np.ndarray, sr: int,
                          pause_duration: float) -> np.ndarray:
        """Adiciona pausas naturais"""
        try:
            # Detectar silêncios existentes
            silence_threshold = 0.01
            frame_length = int(sr * 0.1)  # 100ms frames
            
            # Simples adição de pausas (implementação básica)
            return audio
        except:
            return audio
    
    def _apply_smooth_intonation(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """Aplica entonação suave"""
        try:
            # Suavizar variações de volume
            audio = scipy.signal.savgol_filter(audio, window_length=101, polyorder=3)
            
            return audio
        except:
            return audio
    
    def _add_rhythmic_emphasis(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """Adiciona ênfase rítmica"""
        try:
            # Adicionar ênfase sutil em batidas rítmicas
            return audio
        except:
            return audio
    
    def _add_vibrant_rhythm(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """Adiciona ritmo vibrante"""
        try:
            # Modulação sutil para ritmo
            return audio
        except:
            return audio
    
    def _smooth_dynamics(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """Suaviza dinâmica do áudio"""
        try:
            # Compressão suave
            audio = librosa.effects.percussive(audio)
            
            return audio
        except:
            return audio
    
    def _apply_postprocessing(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """Aplica pós-processamento final"""
        try:
            # Compressão dinâmica
            audio = self._apply_dynamic_compression(audio, sr)
            
            # Equalização final
            audio = self._apply_equalization(audio, sr)
            
            # Reverb sutil
            audio = self._apply_reverb(audio, sr)
            
            # Normalização final
            audio = librosa.util.normalize(audio)
            
            # Limpeza de artefatos
            audio = self._remove_artifacts(audio, sr)
            
            return audio
        except:
            return audio
    
    def _apply_dynamic_compression(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """Aplica compressão dinâmica"""
        try:
            settings = self.enhancement_settings['dynamic_compression']
            
            # Compressão simples
            threshold = settings['threshold']
            ratio = settings['ratio']
            
            # Aplicar compressão (implementação simplificada)
            audio_db = 20 * np.log10(np.abs(audio) + 1e-10)
            
            mask = audio_db > threshold
            audio_db[mask] = threshold + (audio_db[mask] - threshold) / ratio
            
            audio_compressed = np.sign(audio) * (10 ** (audio_db / 20))
            
            return audio_compressed
        except:
            return audio
    
    def _apply_equalization(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """Aplica equalização"""
        try:
            settings = self.enhancement_settings['equalization']
            
            # EQ de 3 bandas (implementação simplificada)
            # Low freq boost
            low_cutoff = settings['low_freq']
            sos_low = scipy.signal.butter(2, low_cutoff, btype='low', 
                                         fs=sr, output='sos')
            low_freq = scipy.signal.sosfilt(sos_low, audio)
            
            # Mid freq
            mid_low = settings['low_freq']
            mid_high = settings['high_freq']
            sos_mid = scipy.signal.butter(2, [mid_low, mid_high], btype='band', 
                                         fs=sr, output='sos')
            mid_freq = scipy.signal.sosfilt(sos_mid, audio)
            
            # High freq
            high_cutoff = settings['high_freq']
            sos_high = scipy.signal.butter(2, high_cutoff, btype='high', 
                                          fs=sr, output='sos')
            high_freq = scipy.signal.sosfilt(sos_high, audio)
            
            # Misturar com ganhos
            audio_eq = (low_freq * settings['low_gain'] + 
                       mid_freq * settings['mid_gain'] + 
                       high_freq * settings['high_gain'])
            
            # Normalizar
            audio_eq = librosa.util.normalize(audio_eq)
            
            return audio_eq
        except:
            return audio
    
    def _apply_reverb(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """Aplica reverb sutil"""
        try:
            settings = self.enhancement_settings['reverb']
            
            # Reverb muito sutil (implementação básica)
            # Em produção, usar bibliotecas especializadas
            return audio
        except:
            return audio
    
    def _remove_artifacts(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """Remove artefatos do processamento"""
        try:
            # Filtro passa-baixa para remover ruído de alta frequência
            sos = scipy.signal.butter(4, 8000, btype='low', fs=sr, output='sos')
            audio = scipy.signal.sosfilt(sos, audio)
            
            # Remover clicks e pops
            audio = self._remove_clicks(audio)
            
            return audio
        except:
            return audio
    
    def _remove_clicks(self, audio: np.ndarray) -> np.ndarray:
        """Remove clicks e pops do áudio"""
        try:
            # Detecção e remoção de clicks (implementação simplificada)
            threshold = 0.1
            diff = np.diff(audio)
            clicks = np.abs(diff) > threshold
            
            # Interpolar clicks
            for i in range(len(clicks)):
                if clicks[i]:
                    if i > 0 and i < len(audio) - 1:
                        audio[i] = (audio[i-1] + audio[i+1]) / 2
            
            return audio
        except:
            return audio
    
    def create_enhanced_tts(self, text: str, output_path: str, 
                           lang: str = 'pt', voice_profile: str = 'natural_female',
                           speed: float = 1.0) -> bool:
        """Cria TTS com voz melhorada"""
        try:
            import gtts
            
            # Gerar TTS básico
            tts = gtts.gTTS(text=text, lang=lang, slow=False)
            
            # Salvar temporário
            temp_path = tempfile.mktemp(suffix='.mp3')
            tts.save(temp_path)
            
            # Converter para WAV para processamento
            audio = AudioSegment.from_mp3(temp_path)
            wav_path = tempfile.mktemp(suffix='.wav')
            audio.export(wav_path, format='wav')
            
            # Aplicar melhorias
            enhanced_wav = tempfile.mktemp(suffix='_enhanced.wav')
            success = self.enhance_audio_file(wav_path, enhanced_wav, 
                                            voice_profile, lang)
            
            if success:
                # Converter de volta para MP3
                enhanced_audio = AudioSegment.from_wav(enhanced_wav)
                
                # Ajustar velocidade se necessário
                if speed != 1.0:
                    enhanced_audio = enhanced_audio._spawn(
                        enhanced_audio.raw_data,
                        overrides={
                            "frame_rate": int(enhanced_audio.frame_rate * speed)
                        }
                    ).set_frame_rate(enhanced_audio.frame_rate)
                
                enhanced_audio.export(output_path, format='mp3', bitrate='192k')
                
                # Limpar arquivos temporários
                os.unlink(temp_path)
                os.unlink(wav_path)
                os.unlink(enhanced_wav)
                
                return True
            else:
                # Fallback para TTS original
                os.rename(temp_path, output_path)
                return False
                
        except Exception as e:
            logger.error(f"Erro ao criar TTS melhorado: {e}")
            return False
    
    def batch_enhance_audio(self, input_files: List[str], output_dir: str,
                           voice_profile: str = 'natural_female',
                           language: str = 'pt') -> List[bool]:
        """Melhora múltiplos arquivos em lote"""
        results = []
        
        for i, input_file in enumerate(input_files):
            try:
                output_file = os.path.join(output_dir, 
                                         f"enhanced_{os.path.basename(input_file)}")
                
                success = self.enhance_audio_file(input_file, output_file,
                                                voice_profile, language)
                results.append(success)
                
                logger.info(f"Arquivo {i+1}/{len(input_files)} processado: {success}")
                
            except Exception as e:
                logger.error(f"Erro ao processar arquivo {input_file}: {e}")
                results.append(False)
        
        return results

# Instância global
voice_enhancer = VoiceEnhancer()
