import os
import gtts
import tempfile
import logging
from typing import Dict, List, Optional
import json
from datetime import datetime

logger = logging.getLogger(__name__)

class GTTSVoiceEnhancer:
    """Melhorador de voz usando apenas parâmetros do GTTS"""
    
    def __init__(self):
        self.voice_profiles = self._load_voice_profiles()
        print("GTTSVoiceEnhancer inicializado!")
    
    def _load_voice_profiles(self) -> Dict[str, Dict]:
        """Carrega perfis de voz baseados em parâmetros GTTS"""
        return {
            'natural_female': {
                'use_slow': False,
                'lang_modifier': 'pt',
                'text_processing': 'add_pauses',
                'description': 'Voz feminina mais natural com pausas'
            },
            'natural_male': {
                'use_slow': False,
                'lang_modifier': 'pt',
                'text_processing': 'clear_pauses',
                'description': 'Voz masculina mais direta (pausas menores)'
            },
            'storyteller': {
                'use_slow': False,
                'lang_modifier': 'pt',
                'text_processing': 'storyteller_pauses',
                'description': 'Narrador profissional com entonação'
            },
            'professional': {
                'use_slow': False,
                'lang_modifier': 'pt',
                'text_processing': 'clear_pauses',
                'description': 'Voz profissional clara e direta'
            },
            'emotional': {
                'use_slow': False,
                'lang_modifier': 'pt',
                'text_processing': 'emotional_pauses',
                'description': 'Voz emocional expressiva'
            },
            'slow_natural': {
                'use_slow': True,
                'lang_modifier': 'pt',
                'text_processing': 'add_pauses',
                'description': 'Voz lenta e natural'
            },
            'fast_clear': {
                'use_slow': False,
                'lang_modifier': 'pt',
                'text_processing': 'minimal_pauses',
                'description': 'Voz rápida e clara'
            }
        }
    
    def process_text_for_profile(self, text: str, profile_name: str) -> str:
        """Processa texto baseado no perfil de voz"""
        if profile_name not in self.voice_profiles:
            profile_name = 'natural_female'
        
        profile = self.voice_profiles[profile_name]
        processing = profile.get('text_processing', 'add_pauses')
        
        # Remover caracteres problemáticos
        import re
        text = re.sub(r'[^\w\s\.\,\!\?\;\:\-\n\r\'\"áàâãéêíóôõúçÁÀÂÃÉÊÍÓÔÕÚÇ]', '', text)
        
        # Aplicar processamento baseado no perfil
        if processing == 'add_pauses':
            # Adicionar pausas naturais
            text = text.replace('.', '. ').replace('!', '! ').replace('?', '? ')
            text = re.sub(r'([,.!?])\s*', r'\1\n', text)  # Pausa após pontuação
            
        elif processing == 'storyteller_pauses':
            # Pausas mais longas para narrativa
            text = text.replace('.', '.\n\n').replace('!', '!\n').replace('?', '?\n')
            
        elif processing == 'clear_pauses':
            # Pausas mínimas e claras
            text = re.sub(r'\s+', ' ', text)  # Normalizar espaços
            text = text.replace('.', '. ').replace('!', '! ').replace('?', '? ')
            
        elif processing == 'emotional_pauses':
            # Pausas expressivas
            text = text.replace('.', '... ').replace('!', '! ').replace('?', '?... ')
            
        elif processing == 'minimal_pauses':
            # Mínimo de pausas
            text = re.sub(r'\s+', ' ', text)
            text = text.replace('. ', '.').replace('! ', '!').replace('? ', '?')
        
        # Limitar tamanho do texto para GTTS
        if len(text) > 5000:
            text = text[:5000] + "..."
        
        return text.strip()
    
    def create_enhanced_tts(self, text: str, output_path: str, 
                           lang: str = 'pt', voice_profile: str = 'natural_female',
                           speed: float = 1.0) -> bool:
        """Cria TTS com voz melhorada usando GTTS"""
        try:
            print(f"🎤 Criando TTS melhorado GTTS: {voice_profile}")
            
            # Obter perfil de voz
            if voice_profile not in self.voice_profiles:
                voice_profile = 'natural_female'
            
            profile = self.voice_profiles[voice_profile]
            
            # Processar texto baseado no perfil
            processed_text = self.process_text_for_profile(text, voice_profile)
            
            # Ajustar velocidade com parâmetro slow do GTTS
            use_slow = profile.get('use_slow', False)
            if speed < 0.7:
                use_slow = True  # Usar modo lento para velocidades muito baixas
            elif speed > 1.3:
                # Para velocidades altas, processamos o texto para ser mais rápido
                processed_text = self.process_text_for_profile(text, 'fast_clear')
            
            print(f"📝 Texto processado: {len(processed_text)} caracteres")
            print(f"🐌 Modo lento: {use_slow}")
            print(f"⚡ Velocidade solicitada: {speed}x")
            
            # Gerar TTS com GTTS
            tts = gtts.gTTS(text=processed_text, lang=lang, slow=use_slow)
            
            # Salvar arquivo
            tts.save(output_path)
            
            print(f"✅ TTS GTTS melhorado salvo: {output_path}")
            
            # Verificar se arquivo foi criado
            if os.path.exists(output_path):
                file_size = os.path.getsize(output_path)
                print(f"📊 Tamanho do arquivo: {file_size} bytes")
                return True
            else:
                print("❌ Arquivo não foi criado")
                return False
            
        except Exception as e:
            print(f"❌ Erro ao criar TTS melhorado: {e}")
            return False
    
    def get_available_profiles(self) -> Dict[str, str]:
        """Retorna perfis disponíveis com descrições"""
        return {k: v['description'] for k, v in self.voice_profiles.items()}
    
    def test_profile(self, profile_name: str) -> bool:
        """Testa um perfil específico"""
        try:
            temp_file = tempfile.mktemp(suffix='.mp3')
            test_text = "Olá, este é um teste do perfil de voz " + profile_name + "."
            
            success = self.create_enhanced_tts(
                text=test_text,
                output_path=temp_file,
                lang='pt',
                voice_profile=profile_name,
                speed=1.0
            )
            
            # Limpar arquivo temporário
            try:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
            except:
                pass
            
            return success
            
        except Exception as e:
            print(f"❌ Erro ao testar perfil {profile_name}: {e}")
            return False

# Instância global
gts_voice_enhancer = GTTSVoiceEnhancer()
