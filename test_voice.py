import requests
import tempfile
import os

def test_voice_conversion():
    """Testa a conversão com diferentes vozes"""
    
    # Criar um arquivo de teste simples
    test_text = "Este é um teste da voz melhorada. Precisamos verificar se está funcionando corretamente."
    
    # Salvar como arquivo TXT
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write(test_text)
        test_file_path = f.name
    
    try:
        # Testar com voz padrão
        print("🔊 Testando com voz PADRÃO...")
        with open(test_file_path, 'rb') as f:
            files = {'file': f}
            data = {
                'lang': 'pt',
                'speed': '1.0',
                'voice_type': 'default',
                'enhanced_voice': 'default'
            }
            response = requests.post('http://localhost:5000/upload', files=files, data=data)
        
        if response.status_code == 200:
            result = response.json()
            conversion_id = result['conversion_id']
            print(f"✅ Conversão padrão iniciada: {conversion_id}")
            
            # Aguardar conclusão
            import time
            for i in range(30):  # 30 segundos timeout
                status_response = requests.get(f'http://localhost:5000/status/{conversion_id}')
                if status_response.status_code == 200:
                    status = status_response.json()
                    print(f"📊 Status: {status['status']} - {status['progress']}% - {status['message']}")
                    if status['status'] == 'completed':
                        break
                time.sleep(1)
        else:
            print(f"❌ Erro na conversão padrão: {response.text}")
        
        # Testar com voz melhorada
        print("\n🎙️ Testando com voz MELHORADA...")
        with open(test_file_path, 'rb') as f:
            files = {'file': f}
            data = {
                'lang': 'pt',
                'speed': '1.0',
                'voice_type': 'default',
                'enhanced_voice': 'natural_female'
            }
            response = requests.post('http://localhost:5000/upload', files=files, data=data)
        
        if response.status_code == 200:
            result = response.json()
            conversion_id = result['conversion_id']
            print(f"✅ Conversão melhorada iniciada: {conversion_id}")
            
            # Aguardar conclusão
            for i in range(30):
                status_response = requests.get(f'http://localhost:5000/status/{conversion_id}')
                if status_response.status_code == 200:
                    status = status_response.json()
                    print(f"📊 Status: {status['status']} - {status['progress']}% - {status['message']}")
                    if status['status'] == 'completed':
                        break
                time.sleep(1)
        else:
            print(f"❌ Erro na conversão melhorada: {response.text}")
        
        print("\n🎯 Teste concluído! Verifique os logs do servidor para ver as diferenças.")
        
    finally:
        # Limpar arquivo temporário
        try:
            os.unlink(test_file_path)
        except:
            pass

if __name__ == "__main__":
    test_voice_conversion()
