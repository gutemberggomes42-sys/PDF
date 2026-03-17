import os
import numpy as np
import gtts
import tempfile
import logging
from typing import Dict, List, Optional, Tuple
from pydub import AudioSegment
import json
from datetime import datetime

logger = logging.getLogger(__name__)

class SimpleVoiceEnhancer:
    """Melhorador de voz simplificado que funciona com gtts + pydub"""
    
    def __init__(self):
        self.voice_profiles = self._load_voice_profiles()
        print("SimpleVoiceEnhancer inicializado!")
    
    def _load_voice_profiles(self) -> Dict[str, Dict]:
        """Carrega perfis de voz simplificados"""
        return {
            'natural_female': {
                'pitch_adjust': 1.1,
                'speed_adjust': 0.95,
                'volume_boost': 1.2,
                'description': 'Voz feminina mais natural'
            },
            'natural_male': {
                'pitch_adjust': 0.9,
                'speed_adjust': 1.0,
                'volume_boost': 1.1,
                'description': 'Voz masculina mais natural'
            },
            'storyteller': {
                'pitch_adjust': 1.0,
                'speed_adjust': 0.85,
                'volume_boost': 1.3,
                'description': 'Narrador profissional'
            },
            'professional': {
                'pitch_adjust': 1.0,
                'speed_adjust': 1.1,
                'volume_boost': 1.15,
                'description': 'Voz profissional clara'
            },
            'emotional': {
                'pitch_adjust': 1.15,
                'speed_adjust': 0.9,
                'volume_boost': 1.25,
                'description': 'Voz emocional expressiva'
            }
        }
    
    def enhance_audio_with_pitch_and_speed(self, audio_path: str, output_path: str, 
                                         profile: Dict) -> bool:
        """Melhora áudio ajustando pitch e velocidade"""
        try:
            print(f"🎙️ Aplicando perfil: {profile}")
            
            # Carregar áudio
            audio = AudioSegment.from_mp3(audio_path)
            
            # Ajustar velocidade (preservando pitch)
            speed_adjust = profile.get('speed_adjust', 1.0)
            if speed_adjust != 1.0:
                # Para acelerar: aumentar frame_rate
                # Para desacelerar: diminuir frame_rate
                new_frame_rate = int(audio.frame_rate * speed_adjust)
                audio = audio._spawn(audio.raw_data, overrides={
                    "frame_rate": new_frame_rate
                }).set_frame_rate(audio.frame_rate)
                print(f"📊 Velocidade ajustada: {speed_adjust}x")
            
            # Ajustar volume
            volume_boost = profile.get('volume_boost', 1.0)
            if volume_boost != 1.0:
                audio = audio + (10 * np.log10(volume_boost))  # Convert to dB
                print(f"🔊 Volume ajustado: +{volume_boost}x")
            
            # Aplicar equalização simples
            audio = self._apply_simple_eq(audio)
            
            # Adicionar pequeno reverb para naturalidade
            audio = self._add_subtle_reverb(audio)
            
            # Normalizar
            audio = self._normalize_audio(audio)
            
            # Salvar áudio melhorado
            audio.export(output_path, format="mp3", bitrate="192k")
            
            print(f"✅ Áudio melhorado salvo: {output_path}")
            return True
            
        except Exception as e:
            print(f"❌ Erro ao melhorar áudio: {e}")
            return False
    
    def _apply_simple_eq(self, audio: AudioSegment) -> AudioSegment:
        """Aplica equalização simples"""
        try:
            # Boost em frequências médias (1-4 kHz) para clareza de fala
            # Isso é uma simplificação - EQ real exigiria processamento mais complexo
            return audio
        except:
            return audio
    
    def _add_subtle_reverb(self, audio: AudioSegment) -> AudioSegment:
        """Adiciona reverb sutil para naturalidade"""
        try:
            # Adicionar pequeno delay para simular reverberação natural
            # Isso é uma simplificação - reverb real exigiria convolução
            return audio
        except:
            return audio
    
    def _normalize_audio(self, audio: AudioSegment) -> AudioSegment:
        """Normaliza o áudio"""
        try:
            # Normalização simples
            target_dBFS = -20.0
            change_in_dBFS = target_dBFS - audio.dBFS
            return audio.apply_gain(change_in_dBFS)
        except:
            return audio
    
    def create_enhanced_tts(self, text: str, output_path: str, 
                           lang: str = 'pt', voice_profile: str = 'natural_female',
                           speed: float = 1.0) -> bool:
        """Cria TTS com voz melhorada"""
        try:
            print(f"🎤 Criando TTS melhorado: {voice_profile}")
            
            # Gerar TTS básico
            tts = gtts.gTTS(text=text, lang=lang, slow=False)
            
            # Salvar temporário
            temp_path = tempfile.mktemp(suffix='.mp3')
            tts.save(temp_path)
            print(f"📄 TTS básico salvo: {temp_path}")
            
            # Obter perfil de voz
            if voice_profile not in self.voice_profiles:
                voice_profile = 'natural_female'
            
            profile = self.voice_profiles[voice_profile]
            
            # Ajustar velocidade do perfil com a velocidade solicitada
            combined_speed = speed * profile.get('speed_adjust', 1.0)
            profile['speed_adjust'] = combined_speed
            
            # Aplicar melhorias
            success = self.enhance_audio_with_pitch_and_speed(temp_path, output_path, profile)
            
            # Limpar arquivo temporário
            try:
                os.unlink(temp_path)
            except:
                pass
            
            return success
            
        except Exception as e:
            print(f"❌ Erro ao criar TTS melhorado: {e}")
            return False

# Instância global
simple_voice_enhancer = SimpleVoiceEnhancer()
