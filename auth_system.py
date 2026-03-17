import os
import jwt
import bcrypt
import secrets
import base64
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, current_app
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import hashlib
import sqlite3
try:
    import redis
except Exception:
    redis = None
import json
import logging

logger = logging.getLogger(__name__)

class AuthenticationSystem:
    """Sistema de autenticação e segurança avançado"""
    
    def __init__(self, app=None, redis_client=None):
        self.app = app
        self.redis_client = redis_client
        self.db_path = 'users.db'
        self.encryption_key = None
        self.init_db()
        
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Inicializa com app Flask"""
        app.config.setdefault('JWT_SECRET_KEY', secrets.token_urlsafe(32))
        app.config.setdefault('JWT_ACCESS_TOKEN_EXPIRES', timedelta(hours=1))
        app.config.setdefault('JWT_REFRESH_TOKEN_EXPIRES', timedelta(days=30))
        app.config.setdefault('ENCRYPTION_KEY', self._generate_encryption_key())
        
        self.encryption_key = app.config['ENCRYPTION_KEY']
    
    def _generate_encryption_key(self):
        """Gera chave de criptografia"""
        password = os.environ.get('MASTER_KEY', secrets.token_urlsafe(32)).encode()
        salt = os.urandom(16)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password))
        return key
    
    def init_db(self):
        """Inicializa banco de dados SQLite"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Tabela de usuários
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                is_premium BOOLEAN DEFAULT 0,
                subscription_expires TIMESTAMP,
                api_key TEXT UNIQUE,
                failed_login_attempts INTEGER DEFAULT 0,
                locked_until TIMESTAMP,
                two_factor_secret TEXT,
                preferences TEXT
            )
        ''')
        
        # Tabela de sessões
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                ip_address TEXT,
                user_agent TEXT,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Tabela de auditoria
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT NOT NULL,
                resource TEXT,
                ip_address TEXT,
                user_agent TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                success BOOLEAN,
                details TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Tabela de arquivos criptografados
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS encrypted_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                encrypted_path TEXT NOT NULL,
                original_hash TEXT NOT NULL,
                encryption_iv TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def hash_password(self, password, salt=None):
        """Gera hash de senha com bcrypt"""
        if salt is None:
            salt = bcrypt.gensalt()
        
        password_hash = bcrypt.hashpw(password.encode('utf-8'), salt)
        return password_hash, salt
    
    def verify_password(self, password, stored_hash):
        """Verifica senha"""
        try:
            return bcrypt.checkpw(password.encode('utf-8'), stored_hash)
        except:
            return False
    
    def generate_tokens(self, user_id):
        """Gera tokens JWT de acesso e refresh"""
        access_token = jwt.encode({
            'user_id': user_id,
            'type': 'access',
            'exp': datetime.utcnow() + current_app.config['JWT_ACCESS_TOKEN_EXPIRES'],
            'iat': datetime.utcnow()
        }, current_app.config['JWT_SECRET_KEY'], algorithm='HS256')
        
        refresh_token = jwt.encode({
            'user_id': user_id,
            'type': 'refresh',
            'exp': datetime.utcnow() + current_app.config['JWT_REFRESH_TOKEN_EXPIRES'],
            'iat': datetime.utcnow()
        }, current_app.config['JWT_SECRET_KEY'], algorithm='HS256')
        
        return {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'expires_in': int(current_app.config['JWT_ACCESS_TOKEN_EXPIRES'].total_seconds())
        }
    
    def verify_token(self, token, token_type='access'):
        """Verifica token JWT"""
        try:
            payload = jwt.decode(
                token, 
                current_app.config['JWT_SECRET_KEY'], 
                algorithms=['HS256']
            )
            
            if payload.get('type') != token_type:
                return None
            
            # Verificar se token está na blacklist
            if self.redis_client:
                blacklist_key = f"blacklist:{token}"
                if self.redis_client.exists(blacklist_key):
                    return None
            
            return payload
        
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None
    
    def encrypt_file(self, file_path, user_id):
        """Criptografa arquivo para usuário"""
        try:
            # Gerar IV para criptografia
            iv = os.urandom(16)
            
            # Ler arquivo
            with open(file_path, 'rb') as f:
                file_data = f.read()
            
            # Criptografar
            fernet = Fernet(self.encryption_key)
            encrypted_data = fernet.encrypt(file_data)
            
            # Salvar arquivo criptografado
            encrypted_filename = f"encrypted_{secrets.token_urlsafe(16)}.bin"
            encrypted_path = os.path.join('encrypted_files', encrypted_filename)
            
            os.makedirs('encrypted_files', exist_ok=True)
            with open(encrypted_path, 'wb') as f:
                f.write(iv + encrypted_data)
            
            # Salvar metadados no banco
            original_hash = hashlib.sha256(file_data).hexdigest()
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO encrypted_files 
                (user_id, filename, encrypted_path, original_hash, encryption_iv, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, os.path.basename(file_path), encrypted_path, 
                   original_hash, iv.hex(), datetime.utcnow() + timedelta(days=30)))
            conn.commit()
            conn.close()
            
            return {
                'success': True,
                'encrypted_path': encrypted_path,
                'file_id': cursor.lastrowid
            }
            
        except Exception as e:
            logger.error(f"Erro na criptografia do arquivo: {e}")
            return {'success': False, 'error': str(e)}
    
    def decrypt_file(self, encrypted_path, user_id):
        """Descriptografa arquivo para usuário"""
        try:
            # Ler arquivo criptografado
            with open(encrypted_path, 'rb') as f:
                data = f.read()
            
            # Extrair IV e dados criptografados
            iv = data[:16]
            encrypted_data = data[16:]
            
            # Descriptografar
            fernet = Fernet(self.encryption_key)
            decrypted_data = fernet.decrypt(encrypted_data)
            
            # Salvar arquivo temporário
            temp_path = os.path.join('temp', f"decrypted_{secrets.token_urlsafe(16)}.tmp")
            os.makedirs('temp', exist_ok=True)
            
            with open(temp_path, 'wb') as f:
                f.write(decrypted_data)
            
            return {
                'success': True,
                'temp_path': temp_path
            }
            
        except Exception as e:
            logger.error(f"Erro na descriptografia do arquivo: {e}")
            return {'success': False, 'error': str(e)}
    
    def log_audit(self, user_id, action, resource=None, success=True, details=None):
        """Registra evento de auditoria"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO audit_log 
                (user_id, action, resource, ip_address, user_agent, success, details)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, action, resource, 
                   request.remote_addr, request.headers.get('User-Agent'), 
                   success, json.dumps(details) if details else None))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Erro no registro de auditoria: {e}")
    
    def check_rate_limit(self, user_id, action, limit=10, window=3600):
        """Verifica limite de taxa (rate limiting)"""
        if not self.redis_client:
            return True
        
        key = f"rate_limit:{user_id}:{action}"
        current = self.redis_client.get(key)
        
        if current is None:
            self.redis_client.setex(key, window, 1)
            return True
        
        count = int(current)
        if count >= limit:
            return False
        
        self.redis_client.incr(key)
        self.redis_client.expire(key, window)
        return True
    
    def blacklist_token(self, token):
        """Adiciona token à blacklist"""
        if self.redis_client:
            try:
                payload = jwt.decode(
                    token, 
                    current_app.config['JWT_SECRET_KEY'], 
                    algorithms=['HS256']
                )
                exp = payload.get('exp')
                
                if exp:
                    ttl = exp - int(datetime.utcnow().timestamp())
                    if ttl > 0:
                        blacklist_key = f"blacklist:{token}"
                        self.redis_client.setex(blacklist_key, ttl, '1')
                        return True
            except:
                pass
        
        return False
    
    def generate_api_key(self, user_id):
        """Gera API key para usuário"""
        api_key = f"pk_{secrets.token_urlsafe(32)}"
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE users SET api_key = ? WHERE id = ?
        ''', (api_key, user_id))
        
        conn.commit()
        conn.close()
        
        return api_key
    
    def verify_api_key(self, api_key):
        """Verifica API key"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, username, is_active, is_premium FROM users WHERE api_key = ?
        ''', (api_key,))
        
        user = cursor.fetchone()
        conn.close()
        
        if user and user[2]:  # is_active
            return {
                'user_id': user[0],
                'username': user[1],
                'is_premium': user[3]
            }
        
        return None

# Decoradores de autenticação
auth_system = AuthenticationSystem()

def require_auth(f):
    """Decorador para requerer autenticação"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = None
        
        # Tentar obter do header Authorization
        auth_header = request.headers.get('Authorization')
        if auth_header:
            try:
                token = auth_header.split(' ')[1]
            except IndexError:
                pass
        
        # Tentar obter do cookie
        if not token:
            token = request.cookies.get('access_token')
        
        if not token:
            return jsonify({'error': 'Token não fornecido'}), 401
        
        payload = auth_system.verify_token(token)
        if not payload:
            return jsonify({'error': 'Token inválido ou expirado'}), 401
        
        # Adicionar user_id ao contexto da requisição
        request.current_user_id = payload['user_id']
        
        return f(*args, **kwargs)
    
    return decorated_function

def require_premium(f):
    """Decorador para requerer conta premium"""
    @wraps(f)
    @require_auth
    def decorated_function(*args, **kwargs):
        conn = sqlite3.connect(auth_system.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT is_premium, subscription_expires FROM users WHERE id = ?
        ''', (request.current_user_id,))
        
        user = cursor.fetchone()
        conn.close()
        
        if not user:
            return jsonify({'error': 'Usuário não encontrado'}), 404
        
        is_premium = user[0]
        subscription_expires = user[1]
        
        # Verificar se assinatura está válida
        if subscription_expires:
            expires_date = datetime.fromisoformat(subscription_expires)
            if expires_date < datetime.utcnow():
                is_premium = False
        
        if not is_premium:
            return jsonify({'error': 'Requer conta premium'}), 402
        
        return f(*args, **kwargs)
    
    return decorated_function

def rate_limit(action, limit=10, window=3600):
    """Decorador para rate limiting"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_id = getattr(request, 'current_user_id', None)
            
            if not user_id:
                return jsonify({'error': 'Autenticação requerida'}), 401
            
            if not auth_system.check_rate_limit(user_id, action, limit, window):
                return jsonify({'error': 'Limite de requisições excedido'}), 429
            
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator

# Middleware de segurança
class SecurityMiddleware:
    """Middleware de segurança avançado"""
    
    def __init__(self, app):
        self.app = app
        self.init_middleware()
    
    def init_middleware(self):
        """Inicializa middlewares de segurança"""
        
        @self.app.before_request
        def before_request():
            # Headers de segurança
            response = None
            
            # CSP (Content Security Policy)
            csp = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' cdn.jsdelivr.net cdn.quilljs.com cdn.plot.ly; "
                "style-src 'self' 'unsafe-inline' cdn.jsdelivr.net cdn.quilljs.com; "
                "img-src 'self' data: https:; "
                "font-src 'self' cdn.jsdelivr.net; "
                "connect-src 'self'; "
                "frame-ancestors 'none';"
            )
            
            if response:
                response.headers['Content-Security-Policy'] = csp
            
            # Outros headers de segurança
            if response:
                response.headers['X-Content-Type-Options'] = 'nosniff'
                response.headers['X-Frame-Options'] = 'DENY'
                response.headers['X-XSS-Protection'] = '1; mode=block'
                response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
                response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
                response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        
        @self.app.after_request
        def after_request(response):
            # Remover headers que expõem informações do servidor
            response.headers.pop('Server', None)
            response.headers.pop('X-Powered-By', None)
            
            return response

# Classe para gerenciamento de sessões seguras
class SecureSessionManager:
    """Gerenciador de sessões seguras"""
    
    def __init__(self, redis_client):
        self.redis_client = redis_client
        self.session_timeout = 3600  # 1 hora
    
    def create_session(self, user_id, ip_address, user_agent):
        """Cria sessão segura"""
        session_id = secrets.token_urlsafe(32)
        session_data = {
            'user_id': user_id,
            'ip_address': ip_address,
            'user_agent': user_agent,
            'created_at': datetime.utcnow().isoformat(),
            'last_activity': datetime.utcnow().isoformat()
        }
        
        # Salvar no Redis
        session_key = f"session:{session_id}"
        self.redis_client.setex(
            session_key, 
            self.session_timeout, 
            json.dumps(session_data)
        )
        
        return session_id
    
    def validate_session(self, session_id, ip_address, user_agent):
        """Valida sessão"""
        session_key = f"session:{session_id}"
        session_data = self.redis_client.get(session_key)
        
        if not session_data:
            return None
        
        try:
            session = json.loads(session_data)
            
            # Verificar IP e User-Agent
            if session['ip_address'] != ip_address:
                return None
            
            if session['user_agent'] != user_agent:
                return None
            
            # Atualizar última atividade
            session['last_activity'] = datetime.utcnow().isoformat()
            self.redis_client.setex(
                session_key,
                self.session_timeout,
                json.dumps(session)
            )
            
            return session
            
        except:
            return None
    
    def revoke_session(self, session_id):
        """Revoga sessão"""
        session_key = f"session:{session_id}"
        self.redis_client.delete(session_key)
    
    def revoke_all_sessions(self, user_id):
        """Revoga todas as sessões do usuário"""
        pattern = "session:*"
        keys = self.redis_client.keys(pattern)
        
        for key in keys:
            session_data = self.redis_client.get(key)
            if session_data:
                try:
                    session = json.loads(session_data)
                    if session['user_id'] == user_id:
                        self.redis_client.delete(key)
                except:
                    continue
