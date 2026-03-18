from flask import Flask, render_template, request, jsonify, send_file, session, g, after_this_request
from werkzeug.utils import secure_filename
import os
import PyPDF2
from io import BytesIO
import gtts
import tempfile
import uuid
from datetime import datetime, timedelta
import threading
import time
import hashlib
import json
import asyncio
import sqlite3
import mimetypes
import requests
import shutil
import zipfile
import wave
import random
import secrets
import subprocess
import re
from urllib.parse import unquote
try:
    import zipstream
except Exception:
    zipstream = None
try:
    import firebase_admin
    from firebase_admin import credentials as firebase_credentials
    from firebase_admin import firestore as firebase_firestore
    from firebase_admin import storage as firebase_storage
    from firebase_admin import auth as firebase_auth
    FIREBASE_ADMIN_AVAILABLE = True
except Exception:
    firebase_admin = None
    firebase_credentials = None
    firebase_firestore = None
    firebase_storage = None
    firebase_auth = None
    FIREBASE_ADMIN_AVAILABLE = False
try:
    import docx
except ImportError:
    docx = None
try:
    import pytesseract
    from PIL import Image
except ImportError:
    pytesseract = None
    Image = None

# Enhanced voice (leve) e mesclagem de áudio
try:
    from gts_voice_enhancer import gts_voice_enhancer
    VOICE_ENHANCER_AVAILABLE = True
    ENHANCED_VOICE_PROFILES = gts_voice_enhancer.get_available_profiles()
except Exception:
    gts_voice_enhancer = None
    VOICE_ENHANCER_AVAILABLE = False
    ENHANCED_VOICE_PROFILES = {}

try:
    from pydub import AudioSegment
    try:
        from pydub.utils import which
        FFMPEG_AVAILABLE = bool(which("ffmpeg") or which("ffmpeg.exe") or which("avconv") or which("avconv.exe"))
    except Exception:
        FFMPEG_AVAILABLE = False
    PYDUB_AVAILABLE = True
except Exception:
    AudioSegment = None
    PYDUB_AVAILABLE = False
    FFMPEG_AVAILABLE = False

# Offline TTS support
try:
    import speech
    OFFLINE_TTS_AVAILABLE = True
except ImportError:
    OFFLINE_TTS_AVAILABLE = False

try:
    import win32com.client
    SAPI_AVAILABLE = True
    speaker = win32com.client.Dispatch("SAPI.SpVoice")
except ImportError:
    SAPI_AVAILABLE = False
    speaker = None

try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
    EDGE_TTS_ERROR = ''
except Exception as e:
    edge_tts = None
    EDGE_TTS_AVAILABLE = False
    EDGE_TTS_ERROR = str(e)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200MB para enterprise
app.config['TEMPLATES_AUTO_RELOAD'] = True
try:
    app.jinja_env.auto_reload = True
except Exception:
    pass
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_upload_env = os.environ.get('UPLOAD_FOLDER')
_audio_env = os.environ.get('AUDIO_FOLDER')
_cache_env = os.environ.get('CACHE_FOLDER')
app.config['UPLOAD_FOLDER'] = os.path.abspath(_upload_env) if _upload_env else os.path.join(_BASE_DIR, 'uploads')
app.config['AUDIO_FOLDER'] = os.path.abspath(_audio_env) if _audio_env else os.path.join(_BASE_DIR, 'audio')
app.config['CACHE_FOLDER'] = os.path.abspath(_cache_env) if _cache_env else os.path.join(_BASE_DIR, 'cache')
_db_env = os.environ.get('DB_PATH')
if _db_env:
    app.config['DB_PATH'] = os.path.abspath(_db_env)
else:
    app.config['DB_PATH'] = os.path.join(_BASE_DIR, 'app_data.db')

app.config['FIREBASE_PROJECT_ID'] = os.environ.get('FIREBASE_PROJECT_ID', 'conversao-de-livro-para-audio')
app.config['FIREBASE_WEB_API_KEY'] = os.environ.get('FIREBASE_WEB_API_KEY', 'AIzaSyCaxbSna7_7F5beEDanIMaHrVZ01DCBJsY')

FFMPEG_PATH = ''
FFPROBE_PATH = ''

def _configure_ffmpeg():
    global FFMPEG_AVAILABLE, FFMPEG_PATH, FFPROBE_PATH
    if not PYDUB_AVAILABLE:
        return
    candidates = []
    env_path = os.environ.get('FFMPEG_PATH', '').strip()
    if env_path:
        candidates.append(env_path)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates.extend([
        os.path.join(base_dir, 'ffmpeg', 'bin', 'ffmpeg.exe'),
        os.path.join(base_dir, 'ffmpeg', 'ffmpeg.exe'),
        os.path.join(base_dir, 'bin', 'ffmpeg.exe'),
        os.path.join(base_dir, 'tools', 'ffmpeg.exe'),
        os.path.join(base_dir, 'ffmpeg.exe')
    ])

    for c in candidates:
        if c and os.path.exists(c):
            try:
                AudioSegment.converter = c
            except Exception:
                pass
            FFMPEG_AVAILABLE = True
            FFMPEG_PATH = c
            try:
                base = os.path.dirname(c)
                ffprobe = os.path.join(base, 'ffprobe.exe')
                if os.path.exists(ffprobe):
                    try:
                        AudioSegment.ffprobe = ffprobe
                    except Exception:
                        pass
                    FFPROBE_PATH = ffprobe
            except Exception:
                pass
            return

    try:
        from pydub.utils import which
        found = which("ffmpeg") or which("ffmpeg.exe") or which("avconv") or which("avconv.exe")
        if found:
            try:
                AudioSegment.converter = found
            except Exception:
                pass
            FFMPEG_AVAILABLE = True
            FFMPEG_PATH = found
            try:
                ffprobe_found = which("ffprobe") or which("ffprobe.exe")
                if ffprobe_found:
                    try:
                        AudioSegment.ffprobe = ffprobe_found
                    except Exception:
                        pass
                    FFPROBE_PATH = ffprobe_found
            except Exception:
                pass
            return
    except Exception:
        pass

    FFMPEG_AVAILABLE = False
    FFMPEG_PATH = ''
    FFPROBE_PATH = ''

_configure_ffmpeg()

# Configurações avançadas
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'your-secret-key-here')
app.config['STRIPE_SECRET_KEY'] = os.environ.get('STRIPE_SECRET_KEY', '')
app.config['STRIPE_PUBLISHABLE_KEY'] = os.environ.get('STRIPE_PUBLISHABLE_KEY', '')
app.config['PAYPAL_CLIENT_ID'] = os.environ.get('PAYPAL_CLIENT_ID', '')
app.config['PAYPAL_CLIENT_SECRET'] = os.environ.get('PAYPAL_CLIENT_SECRET', '')

# Create necessary directories
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['AUDIO_FOLDER'], exist_ok=True)
os.makedirs(app.config['CACHE_FOLDER'], exist_ok=True)
os.makedirs('static/icons', exist_ok=True)
os.makedirs('static/splash', exist_ok=True)
os.makedirs('encrypted_files', exist_ok=True)
os.makedirs('temp', exist_ok=True)

# Store processing status
processing_status = {}
DB_LOCK = threading.Lock()
DEMO_RATE = {}
ZIP_LOCK = threading.Lock()
ZIP_STATUS = {}
ZIP_TTL_S = 3600

def _get_control_status(conversion_id):
    st = processing_status.get(conversion_id) or {}
    return (st.get('control_status') or '').strip().lower()

def _set_control_status(conversion_id, control_status):
    if conversion_id not in processing_status:
        return
    processing_status[conversion_id]['control_status'] = (control_status or '').strip().lower()

EDGE_VOICES_CACHE = {
    'loaded_at': 0.0,
    'voices': []
}

FIRESTORE_CLIENT = None
FIREBASE_STORAGE_BUCKET = os.environ.get('FIREBASE_STORAGE_BUCKET') or os.environ.get('FIREBASE_BUCKET') or ''
REQUIRE_AUTH = os.environ.get('REQUIRE_AUTH', '0') not in ('0', 'false', 'False', 'off')

def _firebase_init():
    global FIRESTORE_CLIENT
    if not FIREBASE_ADMIN_AVAILABLE:
        return
    svc_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON')
    svc_file = os.environ.get('FIREBASE_SERVICE_ACCOUNT_FILE') or os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
    if not svc_json and not svc_file:
        FIRESTORE_CLIENT = None
        return
    try:
        if not firebase_admin._apps:
            if svc_json:
                import json as _json
                cred = firebase_credentials.Certificate(_json.loads(svc_json))
                firebase_admin.initialize_app(cred)
            elif svc_file:
                cred = firebase_credentials.Certificate(os.path.abspath(svc_file))
                firebase_admin.initialize_app(cred)
            else:
                firebase_admin.initialize_app()
        FIRESTORE_CLIENT = firebase_firestore.client()
    except Exception:
        FIRESTORE_CLIENT = None

def _verify_id_token(token):
    if FIREBASE_ADMIN_AVAILABLE and firebase_auth:
        _firebase_init()
        if firebase_admin._apps:
            try:
                return firebase_auth.verify_id_token(token)
            except Exception:
                pass

    api_key = app.config.get('FIREBASE_WEB_API_KEY', '')
    project_id = app.config.get('FIREBASE_PROJECT_ID', '')
    if not api_key or not project_id:
        return None

    try:
        resp = requests.post(
            f"https://identitytoolkit.googleapis.com/v1/accounts:lookup?key={api_key}",
            json={'idToken': token},
            timeout=10
        )
        if resp.status_code != 200:
            return None
        data = resp.json() or {}
        users = data.get('users') or []
        if not users:
            return None

        try:
            import base64 as _b64
            parts = token.split('.')
            if len(parts) >= 2:
                payload = parts[1]
                payload += '=' * (-len(payload) % 4)
                decoded = _b64.urlsafe_b64decode(payload.encode('utf-8'))
                claims = json.loads(decoded.decode('utf-8'))
                if claims.get('aud') != project_id:
                    return None
        except Exception:
            return None

        u = users[0]
        return {
            'uid': u.get('localId'),
            'email': u.get('email'),
            'name': u.get('displayName')
        }
    except Exception:
        return None

@app.before_request
def _load_user():
    g.firebase_user = None
    authz = request.headers.get('Authorization', '')
    if authz.startswith('Bearer '):
        token = authz[len('Bearer '):].strip()
        claims = _verify_id_token(token)
        if claims:
            g.firebase_user = {
                'uid': claims.get('uid'),
                'email': claims.get('email'),
                'name': claims.get('name')
            }
            return
    ctk = request.cookies.get('auth_token', '')
    if ctk:
        try:
            token = unquote(ctk).strip()
        except Exception:
            token = str(ctk).strip()
        if token:
            claims = _verify_id_token(token)
            if claims:
                g.firebase_user = {
                    'uid': claims.get('uid'),
                    'email': claims.get('email'),
                    'name': claims.get('name')
                }

def _require_login():
    if not REQUIRE_AUTH:
        return None
    if g.firebase_user is not None:
        return None
    if not FIREBASE_ADMIN_AVAILABLE:
        return jsonify({'error': 'Firebase Admin não disponível no servidor'}), 500
    _firebase_init()
    if not firebase_admin._apps and not app.config.get('FIREBASE_WEB_API_KEY'):
        return jsonify({'error': 'Firebase não configurado no servidor. Configure FIREBASE_SERVICE_ACCOUNT_FILE.'}), 500
    return jsonify({'error': 'Não autenticado. Faça login com Google.'}), 401

def _firebase_bucket():
    if not FIREBASE_ADMIN_AVAILABLE:
        return None
    _firebase_init()
    if not firebase_admin._apps:
        return None
    try:
        bucket_name = (FIREBASE_STORAGE_BUCKET or '').strip()
        if bucket_name:
            return firebase_storage.bucket(bucket_name)
        return firebase_storage.bucket()
    except Exception:
        return None

def _storage_upload(local_path, remote_path, content_type=None):
    bucket = _firebase_bucket()
    if bucket is None:
        return None
    if not os.path.exists(local_path):
        return None

    ct = content_type
    if not ct:
        guessed, _ = mimetypes.guess_type(local_path)
        ct = guessed or 'application/octet-stream'

    blob = bucket.blob(remote_path)
    blob.upload_from_filename(local_path, content_type=ct)

    gs_uri = f"gs://{bucket.name}/{remote_path}"
    signed_url = None
    try:
        signed_url = blob.generate_signed_url(expiration=timedelta(days=7), method='GET')
    except Exception:
        signed_url = None

    return {
        'bucket': bucket.name,
        'path': remote_path,
        'gs_uri': gs_uri,
        'content_type': ct,
        'signed_url': signed_url
    }

def _resolve_audio_path(conversion_id, p, filename=None):
    if p:
        try:
            if os.path.isabs(p) and os.path.exists(p):
                return p
        except Exception:
            pass
        try:
            if not os.path.isabs(p):
                c1 = os.path.join(_BASE_DIR, p)
                if os.path.exists(c1):
                    return c1
        except Exception:
            pass

    if filename:
        safe_conversion = secure_filename(conversion_id)
        safe_name = secure_filename(filename)
        candidates = [
            os.path.join(app.config['AUDIO_FOLDER'], safe_conversion, safe_name),
            os.path.join(app.config['AUDIO_FOLDER'], safe_name),
            os.path.join(_BASE_DIR, 'audio', safe_conversion, safe_name),
            os.path.join(_BASE_DIR, 'audio', safe_name)
        ]
        for c in candidates:
            try:
                if os.path.exists(c):
                    return c
            except Exception:
                continue
    return None

DB_BACKEND = (os.environ.get('DB_BACKEND') or '').strip().lower()
DATABASE_URL = (os.environ.get('DATABASE_URL') or '').strip()
DB_IS_POSTGRES = (DB_BACKEND == 'postgres') or (DATABASE_URL.startswith('postgres://') or DATABASE_URL.startswith('postgresql://'))
if DB_IS_POSTGRES and DATABASE_URL and ('sslmode=' not in DATABASE_URL) and ('railway.internal' not in DATABASE_URL):
    DATABASE_URL = DATABASE_URL + ('&' if '?' in DATABASE_URL else '?') + 'sslmode=require'

def _ph():
    return '%s' if DB_IS_POSTGRES else '?'

def _ph_list(n):
    return ','.join([_ph()] * int(n))

def _db_connect():
    if DB_IS_POSTGRES:
        import psycopg
        from psycopg.rows import dict_row
        return psycopg.connect(DATABASE_URL, row_factory=dict_row)
    conn = sqlite3.connect(app.config['DB_PATH'], check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA synchronous=NORMAL')
    conn.execute('PRAGMA foreign_keys=ON')
    return conn

def _db_init():
    _firebase_init()
    if FIRESTORE_CLIENT is not None:
        return
    with DB_LOCK:
        conn = _db_connect()
        try:
            if DB_IS_POSTGRES:
                conn.execute(
                    '''
                    CREATE TABLE IF NOT EXISTS conversions (
                        conversion_id TEXT PRIMARY KEY,
                        source_filename TEXT,
                        source_type TEXT,
                        book_title TEXT,
                        user_uid TEXT,
                        user_email TEXT,
                        user_name TEXT,
                        created_at TEXT,
                        updated_at TEXT,
                        status TEXT,
                        progress INTEGER,
                        message TEXT,
                        options_json TEXT,
                        chapters_json TEXT,
                        from_cache INTEGER DEFAULT 0,
                        from_edited_text INTEGER DEFAULT 0,
                        source_storage TEXT,
                        source_local_path TEXT,
                        control_status TEXT,
                        merged_file TEXT,
                        merged_storage TEXT,
                        merge_status TEXT,
                        merge_progress INTEGER,
                        merge_message TEXT,
                        client_ip TEXT,
                        user_agent TEXT,
                        share_token TEXT,
                        share_enabled INTEGER,
                        share_expires_at TEXT
                    )
                    '''
                )
                conn.execute(
                    '''
                    CREATE TABLE IF NOT EXISTS pages (
                        id BIGSERIAL PRIMARY KEY,
                        conversion_id TEXT NOT NULL,
                        page_number INTEGER NOT NULL,
                        filename TEXT,
                        full_path TEXT,
                        display_label TEXT,
                        text TEXT,
                        alignment_json TEXT,
                        text_length INTEGER,
                        created_at TEXT,
                        UNIQUE(conversion_id, page_number)
                    )
                    '''
                )
                conn.execute('CREATE INDEX IF NOT EXISTS idx_pages_conversion ON pages(conversion_id)')
                conn.execute(
                    '''
                    CREATE TABLE IF NOT EXISTS upload_sessions (
                        conversion_id TEXT PRIMARY KEY,
                        user_uid TEXT,
                        filename TEXT,
                        temp_path TEXT,
                        total_size BIGINT,
                        received_size BIGINT,
                        created_at TEXT,
                        updated_at TEXT
                    )
                    '''
                )
                conn.execute('CREATE INDEX IF NOT EXISTS idx_upload_sessions_user ON upload_sessions(user_uid)')
                conn.execute(
                    '''
                    CREATE TABLE IF NOT EXISTS conversion_jobs (
                        conversion_id TEXT PRIMARY KEY,
                        status TEXT,
                        attempts INTEGER,
                        last_error TEXT,
                        created_at TEXT,
                        updated_at TEXT
                    )
                    '''
                )
                conn.execute('CREATE INDEX IF NOT EXISTS idx_conversion_jobs_status ON conversion_jobs(status)')
                conn.execute('CREATE INDEX IF NOT EXISTS idx_conversions_share_token ON conversions(share_token)')
            else:
                conn.execute(
                    '''
                    CREATE TABLE IF NOT EXISTS conversions (
                        conversion_id TEXT PRIMARY KEY,
                        source_filename TEXT,
                        source_type TEXT,
                        book_title TEXT,
                        user_uid TEXT,
                        user_email TEXT,
                        user_name TEXT,
                        created_at TEXT,
                        updated_at TEXT,
                        status TEXT,
                        progress INTEGER,
                        message TEXT,
                        options_json TEXT,
                        chapters_json TEXT,
                        from_cache INTEGER DEFAULT 0,
                        from_edited_text INTEGER DEFAULT 0,
                        source_storage TEXT,
                        source_local_path TEXT,
                        control_status TEXT,
                        merged_file TEXT,
                        merged_storage TEXT,
                        merge_status TEXT,
                        merge_progress INTEGER,
                        merge_message TEXT,
                        client_ip TEXT,
                        user_agent TEXT
                    )
                    '''
                )
                conn.execute(
                    '''
                    CREATE TABLE IF NOT EXISTS pages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        conversion_id TEXT NOT NULL,
                        page_number INTEGER NOT NULL,
                        filename TEXT,
                        full_path TEXT,
                        display_label TEXT,
                        text TEXT,
                        alignment_json TEXT,
                        text_length INTEGER,
                        created_at TEXT,
                        UNIQUE(conversion_id, page_number),
                        FOREIGN KEY(conversion_id) REFERENCES conversions(conversion_id) ON DELETE CASCADE
                    )
                    '''
                )
                conn.execute('CREATE INDEX IF NOT EXISTS idx_pages_conversion ON pages(conversion_id)')
                conn.execute(
                    '''
                    CREATE TABLE IF NOT EXISTS upload_sessions (
                        conversion_id TEXT PRIMARY KEY,
                        user_uid TEXT,
                        filename TEXT,
                        temp_path TEXT,
                        total_size INTEGER,
                        received_size INTEGER,
                        created_at TEXT,
                        updated_at TEXT
                    )
                    '''
                )
                conn.execute('CREATE INDEX IF NOT EXISTS idx_upload_sessions_user ON upload_sessions(user_uid)')
                conn.execute(
                    '''
                    CREATE TABLE IF NOT EXISTS conversion_jobs (
                        conversion_id TEXT PRIMARY KEY,
                        status TEXT,
                        attempts INTEGER,
                        last_error TEXT,
                        created_at TEXT,
                        updated_at TEXT
                    )
                    '''
                )
                conn.execute('CREATE INDEX IF NOT EXISTS idx_conversion_jobs_status ON conversion_jobs(status)')
                page_cols = [r['name'] for r in conn.execute("PRAGMA table_info(pages)").fetchall()]
                if 'display_label' not in page_cols:
                    conn.execute("ALTER TABLE pages ADD COLUMN display_label TEXT")
                if 'text' not in page_cols:
                    conn.execute("ALTER TABLE pages ADD COLUMN text TEXT")
                if 'alignment_json' not in page_cols:
                    conn.execute("ALTER TABLE pages ADD COLUMN alignment_json TEXT")
                cols = [r['name'] for r in conn.execute("PRAGMA table_info(conversions)").fetchall()]
                if 'book_title' not in cols:
                    conn.execute("ALTER TABLE conversions ADD COLUMN book_title TEXT")
                if 'user_uid' not in cols:
                    conn.execute("ALTER TABLE conversions ADD COLUMN user_uid TEXT")
                if 'user_email' not in cols:
                    conn.execute("ALTER TABLE conversions ADD COLUMN user_email TEXT")
                if 'user_name' not in cols:
                    conn.execute("ALTER TABLE conversions ADD COLUMN user_name TEXT")
                if 'chapters_json' not in cols:
                    conn.execute("ALTER TABLE conversions ADD COLUMN chapters_json TEXT")
                if 'source_storage' not in cols:
                    conn.execute("ALTER TABLE conversions ADD COLUMN source_storage TEXT")
                if 'source_local_path' not in cols:
                    conn.execute("ALTER TABLE conversions ADD COLUMN source_local_path TEXT")
                if 'control_status' not in cols:
                    conn.execute("ALTER TABLE conversions ADD COLUMN control_status TEXT")
                if 'merged_storage' not in cols:
                    conn.execute("ALTER TABLE conversions ADD COLUMN merged_storage TEXT")
                if 'share_token' not in cols:
                    conn.execute("ALTER TABLE conversions ADD COLUMN share_token TEXT")
                if 'share_enabled' not in cols:
                    conn.execute("ALTER TABLE conversions ADD COLUMN share_enabled INTEGER")
                if 'share_expires_at' not in cols:
                    conn.execute("ALTER TABLE conversions ADD COLUMN share_expires_at TEXT")
                try:
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_conversions_share_token ON conversions(share_token)")
                except Exception:
                    pass
            conn.commit()
        finally:
            conn.close()

def _db_upsert_conversion(conversion_id, **fields):
    if FIRESTORE_CLIENT is not None:
        now = datetime.now().isoformat()
        data = {'conversion_id': conversion_id, 'updated_at': now}
        data.update(fields)
        options_json = data.get('options_json')
        if options_json and 'options' not in data:
            try:
                data['options'] = json.loads(options_json)
            except Exception:
                pass
        chapters_json = data.get('chapters_json')
        if chapters_json and 'chapters_info' not in data:
            try:
                data['chapters_info'] = json.loads(chapters_json)
            except Exception:
                pass
        FIRESTORE_CLIENT.collection('conversions').document(conversion_id).set(data, merge=True)
        return
    now = datetime.now().isoformat()
    base = {
        'conversion_id': conversion_id,
        'updated_at': now
    }
    for k, v in list(fields.items()):
        if isinstance(v, (dict, list)):
            fields[k] = json.dumps(v, ensure_ascii=False)
    base.update(fields)
    cols = list(base.keys())
    vals = [base[c] for c in cols]
    placeholders = _ph_list(len(cols))
    updates = ','.join([f"{c}=excluded.{c}" for c in cols if c != 'conversion_id'])
    with DB_LOCK:
        conn = _db_connect()
        try:
            conn.execute(
                f"INSERT INTO conversions ({','.join(cols)}) VALUES ({placeholders}) "
                f"ON CONFLICT(conversion_id) DO UPDATE SET {updates}",
                vals
            )
            conn.commit()
        finally:
            conn.close()

def _db_upsert_page(conversion_id, page_number, filename, full_path, text_length, text=None, display_label=None, alignment=None):
    if FIRESTORE_CLIENT is not None:
        now = datetime.now().isoformat()
        doc_id = str(int(page_number))
        stored_text = (text or '')
        if len(stored_text) > 15000:
            stored_text = stored_text[:15000]
        stored_alignment = None
        if alignment is not None:
            try:
                stored_alignment = alignment
            except Exception:
                stored_alignment = None
        data = {
            'conversion_id': conversion_id,
            'page_number': int(page_number),
            'filename': filename,
            'full_path': full_path,
            'display_label': display_label,
            'text': stored_text,
            'alignment': stored_alignment,
            'text_length': int(text_length or 0),
            'created_at': now
        }
        FIRESTORE_CLIENT.collection('conversions').document(conversion_id).collection('pages').document(doc_id).set(data, merge=True)
        return
    now = datetime.now().isoformat()
    stored_text = (text or '')
    if len(stored_text) > 15000:
        stored_text = stored_text[:15000]
    stored_alignment_json = None
    if alignment is not None:
        try:
            stored_alignment_json = json.dumps(alignment, ensure_ascii=False)
        except Exception:
            stored_alignment_json = None
    with DB_LOCK:
        conn = _db_connect()
        try:
            ph = _ph_list(9)
            conn.execute(
                f'''
                INSERT INTO pages (conversion_id, page_number, filename, full_path, display_label, text, alignment_json, text_length, created_at)
                VALUES ({ph})
                ON CONFLICT(conversion_id, page_number) DO UPDATE SET
                    filename=excluded.filename,
                    full_path=excluded.full_path,
                    display_label=excluded.display_label,
                    text=excluded.text,
                    alignment_json=excluded.alignment_json,
                    text_length=excluded.text_length
                ''',
                (conversion_id, int(page_number), filename, full_path, display_label, stored_text, stored_alignment_json, int(text_length or 0), now)
            )
            conn.commit()
        finally:
            conn.close()

def _db_get_conversion(conversion_id):
    if FIRESTORE_CLIENT is not None:
        doc = FIRESTORE_CLIENT.collection('conversions').document(conversion_id).get()
        if not doc.exists:
            return None
        d = doc.to_dict() or {}
        d['conversion_id'] = d.get('conversion_id') or conversion_id
        pages = (
            FIRESTORE_CLIENT.collection('conversions')
            .document(conversion_id)
            .collection('pages')
            .order_by('page_number')
            .stream()
        )
        d['pages_info'] = []
        for p in pages:
            pd = p.to_dict() or {}
            d['pages_info'].append({
                'page_number': pd.get('page_number'),
                'filename': pd.get('filename'),
                'full_path': pd.get('full_path'),
                'display_label': pd.get('display_label'),
                'storage': pd.get('storage')
            })
        if d.get('options_json') and 'options' not in d:
            try:
                d['options'] = json.loads(d['options_json'])
            except Exception:
                d['options'] = {}
        return d
    with DB_LOCK:
        conn = _db_connect()
        try:
            row = conn.execute(f'SELECT * FROM conversions WHERE conversion_id={_ph()}', (conversion_id,)).fetchone()
            if not row:
                return None
            pages = conn.execute(
                f'SELECT page_number, filename, full_path, display_label FROM pages WHERE conversion_id={_ph()} ORDER BY page_number ASC',
                (conversion_id,)
            ).fetchall()
            d = dict(row)
            d['pages_info'] = [dict(p) for p in pages]
            if d.get('options_json'):
                try:
                    d['options'] = json.loads(d['options_json'])
                except Exception:
                    d['options'] = {}
            if d.get('chapters_json'):
                try:
                    d['chapters_info'] = json.loads(d['chapters_json'])
                except Exception:
                    d['chapters_info'] = []
            for k in ('source_storage', 'merged_storage'):
                v = d.get(k)
                if isinstance(v, str) and v.strip().startswith('{'):
                    try:
                        d[k] = json.loads(v)
                    except Exception:
                        pass
            return d
        finally:
            conn.close()

def _db_get_pages_map(conversion_id):
    if FIRESTORE_CLIENT is not None:
        return {}
    with DB_LOCK:
        conn = _db_connect()
        try:
            rows = conn.execute(
                f'SELECT page_number, filename, full_path, display_label, alignment_json FROM pages WHERE conversion_id={_ph()}',
                (conversion_id,)
            ).fetchall()
            out = {}
            for r in rows:
                out[int(r['page_number'])] = dict(r)
            return out
        finally:
            conn.close()

def _db_get_page_by_filename(conversion_id, filename):
    if FIRESTORE_CLIENT is not None:
        try:
            doc_id = str(int(filename.rsplit('_', 1)[-1].split('.')[0]))
        except Exception:
            doc_id = None
        if doc_id:
            try:
                pdoc = (
                    FIRESTORE_CLIENT.collection('conversions')
                    .document(conversion_id)
                    .collection('pages')
                    .document(doc_id)
                    .get()
                )
                if pdoc.exists:
                    return pdoc.to_dict() or {}
            except Exception:
                pass
        try:
            pages = (
                FIRESTORE_CLIENT.collection('conversions')
                .document(conversion_id)
                .collection('pages')
                .where('filename', '==', filename)
                .limit(1)
                .stream()
            )
            for p in pages:
                return p.to_dict() or {}
        except Exception:
            return None
        return None
    with DB_LOCK:
        conn = _db_connect()
        try:
            row = conn.execute(
                f'SELECT page_number, filename, full_path, display_label, text, text_length FROM pages WHERE conversion_id={_ph()} AND filename={_ph()} LIMIT 1',
                (conversion_id, filename)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

def _db_update_page_full_path(conversion_id, filename, full_path):
    if FIRESTORE_CLIENT is not None:
        return
    with DB_LOCK:
        conn = _db_connect()
        try:
            conn.execute(
                f'UPDATE pages SET full_path={_ph()} WHERE conversion_id={_ph()} AND filename={_ph()}',
                (full_path, conversion_id, filename)
            )
            conn.commit()
        finally:
            conn.close()

def _db_get_upload_session(conversion_id):
    if FIRESTORE_CLIENT is not None:
        return None
    with DB_LOCK:
        conn = _db_connect()
        try:
            row = conn.execute(f'SELECT * FROM upload_sessions WHERE conversion_id={_ph()}', (conversion_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

def _db_get_conversion_by_share_token(share_token):
    if FIRESTORE_CLIENT is not None:
        try:
            q = FIRESTORE_CLIENT.collection('conversions').where('share_token', '==', share_token).limit(1).stream()
            for doc in q:
                d = doc.to_dict() or {}
                return d
        except Exception:
            return None
        return None
    with DB_LOCK:
        conn = _db_connect()
        try:
            row = conn.execute(f'SELECT * FROM conversions WHERE share_token={_ph()}', (share_token,)).fetchone()
            if not row:
                return None
            d = dict(row)
            if d.get('options_json'):
                try:
                    d['options'] = json.loads(d.get('options_json'))
                except Exception:
                    pass
            if d.get('chapters_json'):
                try:
                    d['chapters_info'] = json.loads(d.get('chapters_json'))
                except Exception:
                    pass
            pages = conn.execute(
                f'SELECT page_number, filename, full_path, display_label FROM pages WHERE conversion_id={_ph()} ORDER BY page_number ASC',
                (d.get('conversion_id'),)
            ).fetchall()
            d['pages_info'] = [dict(p) for p in pages]
            return d
        finally:
            conn.close()

def _db_upsert_upload_session(conversion_id, **fields):
    if FIRESTORE_CLIENT is not None:
        return
    now = datetime.now().isoformat()
    base = {'conversion_id': conversion_id, 'updated_at': now}
    if 'created_at' not in fields:
        fields['created_at'] = fields.get('created_at') or now
    base.update(fields)
    cols = list(base.keys())
    vals = [base[c] for c in cols]
    placeholders = _ph_list(len(cols))
    updates = ','.join([f"{c}=excluded.{c}" for c in cols if c != 'conversion_id'])
    with DB_LOCK:
        conn = _db_connect()
        try:
            conn.execute(
                f"INSERT INTO upload_sessions ({','.join(cols)}) VALUES ({placeholders}) "
                f"ON CONFLICT(conversion_id) DO UPDATE SET {updates}",
                vals
            )
            conn.commit()
        finally:
            conn.close()

def _db_delete_upload_session(conversion_id):
    if FIRESTORE_CLIENT is not None:
        return
    with DB_LOCK:
        conn = _db_connect()
        try:
            conn.execute(f'DELETE FROM upload_sessions WHERE conversion_id={_ph()}', (conversion_id,))
            conn.commit()
        finally:
            conn.close()

def _db_get_job(conversion_id):
    if FIRESTORE_CLIENT is not None:
        return None
    with DB_LOCK:
        conn = _db_connect()
        try:
            row = conn.execute(f'SELECT * FROM conversion_jobs WHERE conversion_id={_ph()}', (conversion_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

def _db_upsert_job(conversion_id, **fields):
    if FIRESTORE_CLIENT is not None:
        return
    now = datetime.now().isoformat()
    base = {'conversion_id': conversion_id, 'updated_at': now}
    if 'created_at' not in fields:
        fields['created_at'] = fields.get('created_at') or now
    base.update(fields)
    cols = list(base.keys())
    vals = [base[c] for c in cols]
    placeholders = _ph_list(len(cols))
    updates = ','.join([f"{c}=excluded.{c}" for c in cols if c != 'conversion_id'])
    with DB_LOCK:
        conn = _db_connect()
        try:
            conn.execute(
                f"INSERT INTO conversion_jobs ({','.join(cols)}) VALUES ({placeholders}) "
                f"ON CONFLICT(conversion_id) DO UPDATE SET {updates}",
                vals
            )
            conn.commit()
        finally:
            conn.close()

def _db_fetch_next_job():
    if FIRESTORE_CLIENT is not None:
        return None
    with DB_LOCK:
        conn = _db_connect()
        try:
            row = conn.execute(
                "SELECT * FROM conversion_jobs WHERE status='queued' ORDER BY created_at ASC LIMIT 1"
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

def _db_delete_job(conversion_id):
    if FIRESTORE_CLIENT is not None:
        return
    with DB_LOCK:
        conn = _db_connect()
        try:
            conn.execute(f'DELETE FROM conversion_jobs WHERE conversion_id={_ph()}', (conversion_id,))
            conn.commit()
        finally:
            conn.close()

_db_init()

def _resume_pending_conversions():
    if FIRESTORE_CLIENT is not None:
        return
    with DB_LOCK:
        conn = _db_connect()
        try:
            rows = conn.execute(
                '''
                SELECT conversion_id, source_filename, book_title, created_at, progress, options_json, user_uid, source_local_path, status, control_status
                FROM conversions
                WHERE status IN ('processing','paused') AND (source_local_path IS NOT NULL AND source_local_path != '')
                ORDER BY updated_at DESC
                LIMIT 3
                '''
            ).fetchall()
        finally:
            conn.close()
    for r in rows:
        cid = r['conversion_id']
        if cid in processing_status:
            continue
        if (r['status'] or '') == 'paused':
            continue
        if (r['control_status'] or '').strip().lower() == 'pause':
            continue
        src = r['source_local_path']
        try:
            if not src or not os.path.exists(src):
                continue
        except Exception:
            continue
        _db_upsert_conversion(cid, status='queued', message='Retomando (na fila)...', control_status='')
        _db_upsert_job(cid, status='queued', attempts=0, last_error=None)

JOB_WORKER_LOCK = threading.Lock()
JOB_WORKER_STARTED = False
JOB_WORKER_MAX_CONCURRENCY = 1
JOB_WORKER_SEM = threading.Semaphore(JOB_WORKER_MAX_CONCURRENCY)

def _job_worker_loop():
    while True:
        try:
            job = _db_fetch_next_job()
            if not job:
                time.sleep(1.0)
                continue
            cid = job.get('conversion_id')
            if not cid:
                time.sleep(0.5)
                continue
            if cid in processing_status and (processing_status.get(cid) or {}).get('status') == 'processing':
                _db_upsert_job(cid, status='running')
                time.sleep(0.5)
                continue

            JOB_WORKER_SEM.acquire()
            try:
                saved = _db_get_conversion(cid)
                if not saved:
                    _db_delete_job(cid)
                    continue
                if (saved.get('control_status') or '').strip().lower() in ('pause', 'cancel'):
                    _db_upsert_job(cid, status='paused')
                    continue
                src = saved.get('source_local_path') or ''
                if not src or not os.path.exists(src):
                    _db_upsert_conversion(cid, status='error', message='Arquivo original não encontrado no servidor.')
                    _db_upsert_job(cid, status='error', last_error='missing_source')
                    continue
                options = saved.get('options') or {}
                if not isinstance(options, dict):
                    options = {}
                processing_status[cid] = {
                    'status': 'processing',
                    'progress': int(saved.get('progress') or 0),
                    'message': saved.get('message') or 'Iniciando processamento...',
                    'filename': saved.get('source_filename'),
                    'book_title': saved.get('book_title'),
                    'created_at': saved.get('created_at') or datetime.now().isoformat(),
                    'options': options,
                    'user_uid': saved.get('user_uid'),
                    'source_local_path': src,
                    'control_status': ''
                }
                _db_upsert_conversion(cid, status='processing', message='Processando...', control_status='')
                _db_upsert_job(cid, status='running', attempts=int(job.get('attempts') or 0) + 1, last_error=None)
                try:
                    process_pdf(cid, src, options)
                except Exception as e:
                    _db_upsert_conversion(cid, status='error', message=f'Erro no processamento: {str(e)}')
                    _db_upsert_job(cid, status='error', last_error=str(e))
                final = _db_get_conversion(cid) or {}
                if (final.get('status') or '') == 'completed':
                    _db_delete_job(cid)
                elif (final.get('status') or '') in ('paused',):
                    _db_upsert_job(cid, status='paused')
                elif (final.get('status') or '') in ('error', 'cancelled'):
                    _db_upsert_job(cid, status='error', last_error=final.get('message'))
                else:
                    _db_upsert_job(cid, status='queued')
            finally:
                try:
                    JOB_WORKER_SEM.release()
                except Exception:
                    pass
        except Exception:
            time.sleep(1.0)

def _start_job_worker():
    global JOB_WORKER_STARTED
    if FIRESTORE_CLIENT is not None:
        return
    with JOB_WORKER_LOCK:
        if JOB_WORKER_STARTED:
            return
        JOB_WORKER_STARTED = True
        th = threading.Thread(target=_job_worker_loop, daemon=True)
        th.start()

try:
    _resume_pending_conversions()
except Exception:
    pass
try:
    _start_job_worker()
except Exception:
    pass

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

ALLOWED_EXTENSIONS = {'pdf', 'docx', 'txt', 'jpg', 'jpeg', 'png', 'tiff'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def build_book_title(filename):
    base = os.path.splitext(os.path.basename(filename or ''))[0].strip()
    if not base:
        base = 'documento'
    base = secure_filename(base)
    if not base:
        base = 'documento'
    return base[:80]

def detect_common_headers_footers(pages_text):
    header_counts = {}
    footer_counts = {}
    total = 0

    for p in pages_text or []:
        text = (p.get('text') or '')
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            continue
        total += 1
        for ln in lines[:3]:
            if 5 <= len(ln) <= 120:
                header_counts[ln] = header_counts.get(ln, 0) + 1
        for ln in lines[-2:]:
            if 1 <= len(ln) <= 60:
                footer_counts[ln] = footer_counts.get(ln, 0) + 1

    if total <= 2:
        return set(), set()

    header = {ln for ln, c in header_counts.items() if c >= int(total * 0.6)}
    footer = {ln for ln, c in footer_counts.items() if c >= int(total * 0.6)}
    return header, footer

def strip_headers_footers(text, header_set, footer_set):
    if not text:
        return ''
    lines = [ln.rstrip() for ln in text.splitlines()]
    out = []
    for ln in lines:
        s = ln.strip()
        if not s:
            out.append('')
            continue
        if header_set and s in header_set:
            continue
        if footer_set and s in footer_set:
            continue
        out.append(ln)
    return '\n'.join(out)

def detect_chapters_from_pages(pages_text):
    import re
    full = '\n\n'.join([(p.get('text') or '') for p in pages_text or []]).strip()
    if not full:
        return []

    lines = [ln.strip() for ln in full.splitlines()]
    pattern = re.compile(r'^(cap[ií]tulo|chapter|unidade|m[oó]dulo|se[cç][aã]o|parte|livro)\s+([0-9ivxlcdm]+)\b[:\-]?\s*(.*)$', re.IGNORECASE)
    numbered = re.compile(r'^(\d{1,2})\s*[\.\-–—:]?\s*(.+)$')
    major = re.compile(r'^(introdu[cç][aã]o|conclus[aã]o|refer[eê]ncias|bibliografia|ap[eê]ndice|anexo|pref[aá]cio|sum[aá]rio)\b.*$', re.IGNORECASE)
    is_all_caps = re.compile(r'^[A-ZÀ-Ü0-9 \-\–—\.\:]{5,80}$')

    chapters = []
    current = None
    chapter_index = 0
    for ln in lines:
        if not ln:
            continue
        m = pattern.match(ln)
        if m:
            chapter_index += 1
            title_tail = (m.group(3) or '').strip()
            title = f"{m.group(1).title()} {m.group(2).upper()}"
            if title_tail:
                title = f"{title} - {title_tail}"
            current = {'chapter_index': chapter_index, 'title': title, 'text_lines': []}
            chapters.append(current)
            continue
        m2 = numbered.match(ln)
        if m2:
            n = int(m2.group(1))
            rest = (m2.group(2) or '').strip()
            if rest and (major.match(rest) or is_all_caps.match(rest.upper()) or rest[:1].isalpha()):
                chapter_index += 1
                title = f"Capítulo {n:02d}"
                if rest:
                    title = f"{title} - {rest}"
                current = {'chapter_index': chapter_index, 'title': title, 'text_lines': []}
                chapters.append(current)
                continue
        if major.match(ln) or is_all_caps.match(ln.upper()):
            if len(ln) <= 80 and len(ln.split()) <= 10:
                chapter_index += 1
                title = ln.title() if major.match(ln) else ln.strip().title()
                current = {'chapter_index': chapter_index, 'title': title, 'text_lines': []}
                chapters.append(current)
                continue
        if current is None:
            current = {'chapter_index': 1, 'title': 'Conteúdo', 'text_lines': []}
            chapters.append(current)
        current['text_lines'].append(ln)

    result = []
    for c in chapters:
        text = '\n'.join(c['text_lines']).strip()
        if not text:
            continue
        result.append({'chapter_index': c['chapter_index'], 'title': c['title'], 'text': text})
    return result

def split_text_chunks(text, max_chars=1800):
    if not text:
        return []
    import re
    t = re.sub(r'\s+', ' ', text).strip()
    if not t:
        return []
    sentences = re.split(r'(?<=[\.\!\?\:])\s+', t)
    chunks = []
    cur = ''
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        if len(s) > max_chars:
            start = 0
            while start < len(s):
                chunks.append(s[start:start + max_chars])
                start += max_chars
            cur = ''
            continue
        if not cur:
            cur = s
            continue
        if len(cur) + 1 + len(s) > max_chars:
            chunks.append(cur.strip())
            cur = s
        else:
            cur = f"{cur} {s}"
    if cur:
        chunks.append(cur.strip())
    return [c for c in chunks if c]

def postprocess_audio_file(path, normalize_audio=False, trim_silence=False):
    if not path or not os.path.exists(path):
        return
    if not PYDUB_AVAILABLE:
        return
    ext = os.path.splitext(path)[1].lower()
    if ext == '.mp3' and not FFMPEG_AVAILABLE:
        return
    try:
        audio = AudioSegment.from_file(path)
    except Exception:
        return

    changed = False
    if trim_silence:
        try:
            from pydub.silence import detect_nonsilent
            thresh = audio.dBFS - 16
            ranges = detect_nonsilent(audio, min_silence_len=450, silence_thresh=thresh)
            if ranges:
                start = max(0, ranges[0][0])
                end = min(len(audio), ranges[-1][1])
                if end > start:
                    audio = audio[start:end]
                    changed = True
        except Exception:
            pass

    if normalize_audio:
        try:
            headroom = -1.0
            gain = headroom - audio.max_dBFS
            if abs(gain) >= 0.1:
                audio = audio.apply_gain(gain)
                changed = True
        except Exception:
            pass

    if not changed:
        return

    try:
        if ext == '.mp3':
            audio.export(path, format='mp3', bitrate='192k')
        elif ext == '.wav':
            audio.export(path, format='wav')
        else:
            audio.export(path)
    except Exception:
        return

def _run_with_timeout(fn, timeout_s):
    out = {'value': None, 'error': None}
    def _runner():
        try:
            out['value'] = fn()
        except Exception as e:
            out['error'] = e
    th = threading.Thread(target=_runner, daemon=True)
    th.start()
    th.join(timeout_s)
    if th.is_alive():
        raise TimeoutError('Operação excedeu o tempo limite')
    if out['error'] is not None:
        raise out['error']
    return out['value']

def tts_to_file(text, out_path, lang='pt', speed=1.0, voice_type='default', enhanced_voice='default', tts_engine='gtts', tts_voice=None, sapi_voice=None, use_offline=False):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    if use_offline:
        try:
            if SAPI_AVAILABLE and str(lang).strip().lower().startswith('pt'):
                out_dir = os.path.dirname(out_path)
                tmp = text_to_speech_offline(text, out_dir, 0, voice_type=voice_type, sapi_voice=sapi_voice)
                if tmp and os.path.exists(tmp):
                    if tmp.lower().endswith('.wav') and out_path.lower().endswith('.mp3'):
                        return tmp
                    if os.path.abspath(tmp) != os.path.abspath(out_path):
                        try:
                            os.replace(tmp, out_path)
                        except Exception:
                            out_path = tmp
                    return out_path if os.path.exists(out_path) else tmp
        except Exception:
            pass
    if tts_engine == 'edge' and tts_voice and EDGE_TTS_AVAILABLE and edge_tts is not None:
        audio_file = out_path
        rate_pct = int((float(speed) - 1.0) * 100)
        if rate_pct < -50:
            rate_pct = -50
        if rate_pct > 100:
            rate_pct = 100
        rate_str = f"{rate_pct:+d}%"
        async def _run():
            communicate = edge_tts.Communicate(text, voice=tts_voice, rate=rate_str)
            await asyncio.wait_for(communicate.save(audio_file), timeout=240)
        try:
            asyncio.run(_run())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(_run())
            finally:
                loop.close()
        return audio_file if os.path.exists(audio_file) else None

    effective_profile = enhanced_voice
    if (not effective_profile or effective_profile == 'default') and voice_type in ('female', 'male'):
        if voice_type == 'female':
            effective_profile = 'natural_female'
        elif voice_type == 'male':
            effective_profile = 'natural_male'

    if VOICE_ENHANCER_AVAILABLE and effective_profile and effective_profile != 'default':
        def _do():
            return gts_voice_enhancer.create_enhanced_tts(
                text=text,
                output_path=out_path,
                lang=lang,
                voice_profile=effective_profile,
                speed=speed
            )
        ok = _run_with_timeout(_do, 240)
        return out_path if ok and os.path.exists(out_path) else None

    slow_flag = float(speed) < 0.8
    def _do_gtts():
        tts = gtts.gTTS(text=text, lang=lang, slow=slow_flag)
        tts.save(out_path)
        return True
    _run_with_timeout(_do_gtts, 240)
    return out_path if os.path.exists(out_path) else None

def tts_to_file_with_alignment(text, out_path, lang='pt', speed=1.0, voice_type='default', enhanced_voice='default', tts_engine='gtts', tts_voice=None, sapi_voice=None, use_offline=False, normalize_audio=False, trim_silence=False):
    if tts_engine == 'edge' and tts_voice and EDGE_TTS_AVAILABLE and edge_tts is not None:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        rate_pct = int((float(speed) - 1.0) * 100)
        if rate_pct < -50:
            rate_pct = -50
        if rate_pct > 100:
            rate_pct = 100
        rate_str = f"{rate_pct:+d}%"

        async def _run_stream():
            communicate = edge_tts.Communicate(text, voice=tts_voice, rate=rate_str)
            alignment = []
            with open(out_path, 'wb') as f:
                async for chunk in communicate.stream():
                    t = chunk.get('type')
                    if t == 'audio':
                        f.write(chunk.get('data') or b'')
                    elif t == 'WordBoundary':
                        offset = chunk.get('offset')
                        text_offset = chunk.get('text_offset')
                        text_length = chunk.get('text_length')
                        word = chunk.get('text')
                        t_ms = None
                        if isinstance(offset, (int, float)):
                            try:
                                t_ms = int(float(offset) / 10000.0)
                            except Exception:
                                t_ms = None
                        alignment.append({
                            't_ms': t_ms,
                            'text_offset': text_offset,
                            'text_length': text_length,
                            'word': word
                        })
            return alignment

        try:
            alignment = asyncio.run(asyncio.wait_for(_run_stream(), timeout=240))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                alignment = loop.run_until_complete(asyncio.wait_for(_run_stream(), timeout=240))
            finally:
                loop.close()

        if os.path.exists(out_path):
            postprocess_audio_file(out_path, normalize_audio=normalize_audio, trim_silence=trim_silence)
            alignment = [a for a in (alignment or []) if a.get('t_ms') is not None and a.get('text_offset') is not None and a.get('text_length') is not None]
            return {'path': out_path, 'alignment': alignment}
        return {'path': None, 'alignment': None}

    p = tts_to_file(
        text,
        out_path,
        lang=lang,
        speed=speed,
        voice_type=voice_type,
        enhanced_voice=enhanced_voice,
        tts_engine=tts_engine,
        tts_voice=tts_voice,
        sapi_voice=sapi_voice,
        use_offline=use_offline
    )
    if p:
        postprocess_audio_file(p, normalize_audio=normalize_audio, trim_silence=trim_silence)
    return {'path': p, 'alignment': None}

def extract_text_from_file(file_path, file_type, options=None):
    """Extract text from different file types"""
    pages_text = []
    if options is None:
        options = {}
    if not isinstance(options, dict):
        options = {}
    
    try:
        if file_type == 'pdf':
            lang = str(options.get('lang') or 'pt').strip().lower()
            use_ocr = bool(options.get('use_ocr', False))
            return extract_text_from_pdf_page_by_page(file_path, lang=lang, use_ocr=use_ocr)
        
        elif file_type == 'docx':
            if not docx:
                raise Exception("Biblioteca python-docx não instalada")
            
            doc = docx.Document(file_path)
            full_text = []
            
            for para in doc.paragraphs:
                if para.text.strip():
                    full_text.append(para.text.strip())
            
            # Split into pages (approximately 500 words per page)
            words = ' '.join(full_text).split()
            page_size = 500
            
            for i in range(0, len(words), page_size):
                page_words = words[i:i+page_size]
                page_text = ' '.join(page_words)
                if page_text.strip():
                    pages_text.append({
                        'page_number': i // page_size + 1,
                        'text': page_text
                    })
            
            return pages_text
        
        elif file_type == 'txt':
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
            
            # Split into pages
            words = content.split()
            page_size = 500
            
            for i in range(0, len(words), page_size):
                page_words = words[i:i+page_size]
                page_text = ' '.join(page_words)
                if page_text.strip():
                    pages_text.append({
                        'page_number': i // page_size + 1,
                        'text': page_text
                    })
            
            return pages_text
        
        else:
            raise Exception(f"Formato de arquivo não suportado: {file_type}")
            
    except Exception as e:
        raise Exception(f"Erro ao extrair texto do arquivo {file_type}: {str(e)}")

def get_file_hash(file_path):
    """Get MD5 hash of file for caching"""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def build_cache_key(file_hash, options):
    lang = str(options.get('lang', 'pt'))
    speed = str(options.get('speed', 1.0))
    voice_type = str(options.get('voice_type', 'default'))
    enhanced_voice = str(options.get('enhanced_voice', 'default'))
    file_type = str(options.get('file_type', 'pdf'))
    split_mode = str(options.get('split_mode', 'chapter'))
    normalize_audio = "1" if bool(options.get('normalize_audio', False)) else "0"
    trim_silence = "1" if bool(options.get('trim_silence', False)) else "0"
    use_offline = "1" if bool(options.get('use_offline', False)) else "0"
    sapi_voice = str(options.get('sapi_voice', ''))
    tts_engine = str(options.get('tts_engine', 'gtts'))
    tts_voice = str(options.get('tts_voice', ''))
    return f"{file_hash}_{lang}_{speed}_{voice_type}_{enhanced_voice}_{split_mode}_{normalize_audio}_{trim_silence}_{use_offline}_{sapi_voice}_{tts_engine}_{tts_voice}_{file_type}"

def check_cache(file_hash, options):
    """Check if conversion exists in cache"""
    cache_key = build_cache_key(file_hash, options)
    cache_file = os.path.join(app.config['CACHE_FOLDER'], cache_key)
    cache_file_json = cache_file + ".json"
    
    for path in (cache_file, cache_file_json):
        if not os.path.exists(path):
            continue
        try:
            with open(path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # Check if audio files still exist
            if all(os.path.exists(path) for path in cache_data['audio_files']):
                return cache_data
        except:
            pass
    
    return None

def save_to_cache(file_hash, options, result_data):
    """Save conversion result to cache"""
    cache_key = build_cache_key(file_hash, options)
    cache_file = os.path.join(app.config['CACHE_FOLDER'], cache_key)
    
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False)
    except:
        pass

def extract_text_from_pdf_page_by_page(pdf_path):
    return extract_text_from_pdf_page_by_page(pdf_path, lang='pt', use_ocr=False)

def _tesseract_lang_for(lang):
    l = (lang or '').strip().lower()
    mapping = {
        'pt': 'por',
        'pt-br': 'por',
        'en': 'eng',
        'es': 'spa',
        'fr': 'fra',
        'de': 'deu',
        'it': 'ita',
        'ru': 'rus',
        'zh': 'chi_sim',
        'ja': 'jpn'
    }
    return mapping.get(l, 'eng')

def _ocr_available():
    if not pytesseract or not Image:
        return False
    try:
        return bool(shutil.which('tesseract'))
    except Exception:
        return False

def _pdf_ocr_available():
    if not _ocr_available():
        return False
    try:
        return bool(shutil.which('pdftoppm'))
    except Exception:
        return False

def _ocr_pdf_page_text(pdf_path, page_number, lang):
    if not _pdf_ocr_available():
        return ''
    ocr_lang = _tesseract_lang_for(lang)
    with tempfile.TemporaryDirectory() as td:
        out_base = os.path.join(td, f"page_{int(page_number)}")
        cmd = ['pdftoppm', '-f', str(int(page_number)), '-l', str(int(page_number)), '-singlefile', '-png', pdf_path, out_base]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        img_path = out_base + '.png'
        if not os.path.exists(img_path):
            return ''
        img = Image.open(img_path)
        try:
            txt = pytesseract.image_to_string(img, lang=ocr_lang, config='--psm 6')
        finally:
            try:
                img.close()
            except Exception:
                pass
        return (txt or '').strip()

def extract_text_from_pdf_page_by_page(pdf_path, lang='pt', use_ocr=False):
    pages_text = []
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            page_count = len(pdf_reader.pages)
            for page_num in range(page_count):
                page = pdf_reader.pages[page_num]
                page_text = ''
                try:
                    page_text = page.extract_text() or ''
                except Exception:
                    page_text = ''
                pages_text.append({
                    'page_number': page_num + 1,
                    'text': (page_text or '').strip()
                })

        non_empty = [p for p in pages_text if (p.get('text') or '').strip()]
        if (not non_empty) and _pdf_ocr_available():
            for p in pages_text:
                p['text'] = _ocr_pdf_page_text(pdf_path, p.get('page_number') or 1, lang)
            return pages_text

        if use_ocr and _pdf_ocr_available():
            min_chars = 15
            for p in pages_text:
                t = (p.get('text') or '').strip()
                if len(t) >= min_chars:
                    continue
                ocr_t = _ocr_pdf_page_text(pdf_path, p.get('page_number') or 1, lang)
                if len(ocr_t) > len(t):
                    p['text'] = ocr_t

        return pages_text
    except Exception as e:
        raise Exception(f"Erro ao extrair texto do PDF: {str(e)}")

def text_to_speech_offline(text, output_dir, page_number, voice_type='default', sapi_voice=None):
    """Convert text to speech using offline SAPI voices"""
    try:
        if not SAPI_AVAILABLE:
            return None
        
        # Clean text for this page
        cleaned_text = clean_text_for_tts(text)
        
        if not cleaned_text.strip():
            return None
        
        print(f"Convertendo página {page_number} offline (SAPI): {len(cleaned_text)} caracteres")
        
        # Create SAPI speaker instance
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        
        voices = speaker.GetVoices()
        if sapi_voice:
            for voice in voices:
                try:
                    if voice.GetDescription() == sapi_voice:
                        speaker.Voice = voice
                        break
                except Exception:
                    pass
        elif voice_type in ('female', 'male'):
            for voice in voices:
                try:
                    if voice_type in voice.GetDescription().lower():
                        speaker.Voice = voice
                        break
                except Exception:
                    pass

        os.makedirs(output_dir, exist_ok=True)

        # Export to WAV file
        wav_file = os.path.join(output_dir, f"pagina_{page_number:03d}_offline.wav")

        stream = win32com.client.Dispatch("SAPI.SpFileStream")
        stream.Open(wav_file, 3, False)
        speaker.AudioOutputStream = stream
        speaker.Speak(cleaned_text)
        stream.Close()

        if PYDUB_AVAILABLE and FFMPEG_AVAILABLE:
            try:
                mp3_file = os.path.join(output_dir, f"pagina_{page_number:03d}_offline.mp3")
                audio = AudioSegment.from_wav(wav_file)
                audio.export(mp3_file, format="mp3", bitrate="192k")
                try:
                    os.remove(wav_file)
                except Exception:
                    pass
                return mp3_file
            except Exception:
                return wav_file

        return wav_file
            
    except Exception as e:
        print(f"Erro ao converter página {page_number} offline: {str(e)}")
        return None

def text_to_speech_page(text, output_dir, page_number, lang='pt', speed=1.0, voice_type='default', enhanced_voice='default', tts_engine='gtts', tts_voice=None, sapi_voice=None, use_offline=False):
    """Convert single page text to speech with speed and voice options"""
    try:
        # Try offline first if requested and available
        if use_offline and SAPI_AVAILABLE and lang == 'pt':
            offline_result = text_to_speech_offline(text, output_dir, page_number, voice_type, sapi_voice=sapi_voice)
            if offline_result:
                return offline_result
        
        # Clean text for this page
        cleaned_text = clean_text_for_tts(text)
        
        if not cleaned_text.strip():
            return None
        
        print(f"Convertendo página {page_number}: {len(cleaned_text)} caracteres (idioma: {lang}, velocidade: {speed}x)")
        
        os.makedirs(output_dir, exist_ok=True)

        # gTTS doesn't support speed directly, but we can use slow=True for slower speech
        # For faster speech, we'll need to use audio processing libraries
        slow_flag = speed < 0.8

        if tts_engine == 'edge' and tts_voice:
            global EDGE_TTS_AVAILABLE, edge_tts, EDGE_TTS_ERROR
            if not EDGE_TTS_AVAILABLE:
                try:
                    import edge_tts as _edge_tts
                    edge_tts = _edge_tts
                    EDGE_TTS_AVAILABLE = True
                    EDGE_TTS_ERROR = ''
                except Exception as e:
                    EDGE_TTS_AVAILABLE = False
                    EDGE_TTS_ERROR = str(e)
            if not EDGE_TTS_AVAILABLE:
                pass
            else:
                audio_file = os.path.join(output_dir, f"pagina_{page_number:03d}_edge.mp3")
                rate_pct = int((float(speed) - 1.0) * 100)
                if rate_pct < -50:
                    rate_pct = -50
                if rate_pct > 100:
                    rate_pct = 100
                rate_str = f"{rate_pct:+d}%"
                async def _run():
                    communicate = edge_tts.Communicate(cleaned_text, voice=tts_voice, rate=rate_str)
                    await communicate.save(audio_file)
                try:
                    asyncio.run(_run())
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    try:
                        loop.run_until_complete(_run())
                    finally:
                        loop.close()
                if os.path.exists(audio_file):
                    return audio_file
        
        effective_profile = enhanced_voice
        if (not effective_profile or effective_profile == 'default') and voice_type in ('female', 'male'):
            if voice_type == 'female':
                effective_profile = 'natural_female'
            elif voice_type == 'male':
                effective_profile = 'natural_male'

        if VOICE_ENHANCER_AVAILABLE and effective_profile and effective_profile != 'default':
            audio_file = os.path.join(output_dir, f"pagina_{page_number:03d}_enhanced.mp3")
            ok = gts_voice_enhancer.create_enhanced_tts(
                text=cleaned_text,
                output_path=audio_file,
                lang=lang,
                voice_profile=effective_profile,
                speed=speed
            )
            if ok and os.path.exists(audio_file):
                return audio_file

        # If page is too long, split it but keep it as one audio file
        max_chars = 2000
        if len(cleaned_text) > max_chars:
            # Split long pages but merge into one file
            chunks = [cleaned_text[i:i+max_chars] for i in range(0, len(cleaned_text), max_chars)]
            temp_files = []
            
            for i, chunk in enumerate(chunks):
                try:
                    tts = gtts.gTTS(text=chunk, lang=lang, slow=slow_flag)
                    temp_file = os.path.join(output_dir, f"pagina_{page_number:03d}_temp_{i}.mp3")
                    tts.save(temp_file)
                    temp_files.append(temp_file)
                except:
                    continue
            
            if temp_files:
                final_file = os.path.join(output_dir, f"pagina_{page_number:03d}.mp3")
                merged = False
                if PYDUB_AVAILABLE and FFMPEG_AVAILABLE:
                    try:
                        combined = AudioSegment.from_mp3(temp_files[0])
                        for temp_file in temp_files[1:]:
                            try:
                                combined += AudioSegment.from_mp3(temp_file)
                            except:
                                pass
                        combined.export(final_file, format="mp3", bitrate="192k")
                        merged = True
                    except Exception:
                        merged = False
                if not merged:
                    import shutil
                    shutil.move(temp_files[0], final_file)
                for temp_file in temp_files:
                    try:
                        if os.path.exists(temp_file):
                            os.remove(temp_file)
                    except:
                        pass
                return final_file
        else:
            # Normal page, convert directly
            tts = gtts.gTTS(text=cleaned_text, lang=lang, slow=slow_flag)
            audio_file = os.path.join(output_dir, f"pagina_{page_number:03d}.mp3")
            tts.save(audio_file)
            return audio_file
            
    except Exception as e:
        print(f"Erro ao converter página {page_number}: {str(e)}")
        return None

def clean_text_for_tts(text):
    t = str(text or '')
    if not t.strip():
        return ''

    t = t.replace('\r\n', '\n').replace('\r', '\n')
    t = re.sub(r'[ \t\f\v]+', ' ', t)
    t = re.sub(r'(\w)-\n(\w)', r'\1\2', t)

    bullet_re = re.compile(r'^(\s*[\-\–—•\*]\s+|\s*\d{1,3}[\.\)]\s+|\s*[a-zA-Z][\.\)]\s+)')
    drop_line_re = re.compile(r'^(?:\d{1,4}|(?i:(p[áa]gina|page))\s*\d{1,4})$')

    parts = []
    for para in re.split(r'\n{2,}', t):
        raw_lines = [ln.strip() for ln in para.split('\n') if ln.strip()]
        if not raw_lines:
            continue
        lines = []
        for raw_ln in raw_lines:
            if drop_line_re.fullmatch(raw_ln):
                continue
            is_bullet = bool(bullet_re.match(raw_ln))
            ln = bullet_re.sub('', raw_ln, count=1) if is_bullet else raw_ln
            ln = re.sub(r'[^\w\s\.\,\!\?\;\:\-\(\)\[\]\/%º°]', '', ln)
            ln = re.sub(r'\s+', ' ', ln).strip()
            if len(ln) <= 2:
                continue
            lines.append((ln, is_bullet))
        if not lines:
            continue

        if any(flag for _, flag in lines):
            for ln, _flag in lines:
                if not re.search(r'[.!?]$', ln):
                    ln += '.'
                parts.append(ln)
        else:
            combined = ' '.join([ln for ln, _flag in lines])
            combined = re.sub(r'\s+', ' ', combined).strip()
            if combined and not re.search(r'[.!?]$', combined):
                combined += '.'
            if combined:
                parts.append(combined)

    out = ' '.join(parts).strip()
    out = re.sub(r'\s+', ' ', out).strip()
    return out

@app.route('/')
def index():
    p = os.path.join(app.root_path, app.template_folder or 'templates', 'index.html')
    resp = send_file(p, conditional=False)
    resp.headers['Content-Type'] = 'text/html; charset=utf-8'
    return resp

@app.route('/sw.js')
def service_worker():
    p = os.path.join(app.root_path, 'static', 'sw.js')
    resp = send_file(p, conditional=False)
    resp.headers['Content-Type'] = 'application/javascript; charset=utf-8'
    resp.headers['Service-Worker-Allowed'] = '/'
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

@app.route('/demo/tts', methods=['POST'])
def demo_tts():
    ip = request.remote_addr or 'unknown'
    now = time.time()
    window_s = 10 * 60
    max_hits = 6
    hits = [t for t in (DEMO_RATE.get(ip) or []) if now - t < window_s]
    if len(hits) >= max_hits:
        DEMO_RATE[ip] = hits
        return jsonify({'error': 'Muitas tentativas. Aguarde alguns minutos e tente novamente.'}), 429
    hits.append(now)
    DEMO_RATE[ip] = hits

    data = request.get_json(silent=True) or {}
    text = (data.get('text') or '').strip()
    if not text:
        return jsonify({'error': 'Texto vazio'}), 400
    if len(text) > 1200:
        return jsonify({'error': 'Texto muito longo para a amostra'}), 400
    lang = (data.get('lang') or 'pt').strip()[:10]
    tts_engine = (data.get('tts_engine') or 'gtts').strip().lower()
    tts_voice = (data.get('tts_voice') or '').strip()
    speed = 1.0

    out_dir = os.path.join(_BASE_DIR, 'temp')
    os.makedirs(out_dir, exist_ok=True)
    suffix = '.mp3'
    fname = f"demo_{int(now)}_{random.randint(1000, 9999)}.mp3"
    out_path = os.path.join(out_dir, fname)

    try:
        res = tts_to_file_with_alignment(
            text,
            out_path,
            lang=lang,
            speed=speed,
            voice_type='default',
            enhanced_voice='default',
            tts_engine=tts_engine,
            tts_voice=tts_voice or None,
            sapi_voice='',
            use_offline=False,
            normalize_audio=False,
            trim_silence=False
        )
        p = res.get('path')
        if not p or not os.path.exists(p):
            return jsonify({'error': 'Não foi possível gerar o áudio'}), 500
    except Exception as e:
        return jsonify({'error': f'Erro ao gerar amostra: {str(e)}'}), 500

    @after_this_request
    def _cleanup(resp):
        try:
            os.remove(out_path)
        except Exception:
            pass
        return resp

    return send_file(out_path, as_attachment=False, mimetype='audio/mpeg', conditional=False)

def _start_conversion_processing(conversion_id, pdf_path, filename, book_title, options, src_remote=None):
    created_at = datetime.now().isoformat()
    try:
        existing = _db_get_conversion(conversion_id)
        if existing and existing.get('created_at'):
            created_at = existing.get('created_at')
    except Exception:
        pass

    processing_status[conversion_id] = {
        'status': 'queued',
        'progress': 0,
        'message': 'Na fila para processar...',
        'filename': filename,
        'book_title': book_title,
        'created_at': created_at,
        'options': options,
        'source_local_path': pdf_path,
        'control_status': ''
    }
    if g.firebase_user:
        processing_status[conversion_id]['user_uid'] = g.firebase_user.get('uid')

    _db_upsert_conversion(
        conversion_id,
        source_filename=filename,
        source_type=options.get('file_type'),
        book_title=book_title,
        user_uid=g.firebase_user.get('uid') if g.firebase_user else None,
        user_email=g.firebase_user.get('email') if g.firebase_user else None,
        user_name=g.firebase_user.get('name') if g.firebase_user else None,
        created_at=created_at,
        status='queued',
        progress=0,
        message=processing_status[conversion_id]['message'],
        options_json=json.dumps(options, ensure_ascii=False),
        source_storage=src_remote,
        source_local_path=pdf_path,
        control_status='',
        client_ip=request.remote_addr,
        user_agent=request.headers.get('User-Agent')
    )
    _db_upsert_job(conversion_id, status='queued', attempts=0, last_error=None)

@app.route('/upload', methods=['POST'])
def upload_file():
    auth_err = _require_login()
    if auth_err:
        return auth_err
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
            'use_offline': request.form.get('use_offline', '0') in ('1', 'true', 'True', 'on'),
            'sapi_voice': request.form.get('sapi_voice', ''),
            'tts_engine': request.form.get('tts_engine', 'gtts'),
            'tts_voice': request.form.get('tts_voice', ''),
            'split_mode': request.form.get('split_mode', 'chapter'),
            'normalize_audio': request.form.get('normalize_audio', '0') in ('1', 'true', 'True', 'on'),
            'trim_silence': request.form.get('trim_silence', '0') in ('1', 'true', 'True', 'on'),
            'file_type': file.filename.rsplit('.', 1)[1].lower()
        }
        
        requested_id = (request.form.get('conversion_id') or '').strip()
        conversion_id = None
        if requested_id:
            import re
            if re.fullmatch(r'[a-fA-F0-9\-]{10,80}', requested_id):
                conversion_id = requested_id
        if not conversion_id:
            conversion_id = str(uuid.uuid4())
        try:
            existing = _db_get_conversion(conversion_id)
            if existing:
                uid = existing.get('user_uid')
                if existing.get('status') == 'uploading' and (not uid or (g.firebase_user and uid == g.firebase_user.get('uid'))):
                    pass
                else:
                    conversion_id = str(uuid.uuid4())
        except Exception:
            pass
        
        # Save uploaded file
        filename = secure_filename(file.filename)
        book_title = build_book_title(filename)
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{conversion_id}_{filename}")
        file.save(pdf_path)

        src_remote = _storage_upload(
            pdf_path,
            f"uploads/{conversion_id}/{filename}",
            content_type=mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        )
        _start_conversion_processing(conversion_id, pdf_path, filename, book_title, options, src_remote=src_remote)
        
        return jsonify({
            'conversion_id': conversion_id,
            'message': 'Arquivo enviado com sucesso. Processando...',
            'options': options
        })
    
    return jsonify({'error': 'Tipo de arquivo não permitido. Apenas PDFs, DOCX e TXT são aceitos.'}), 400

@app.route('/api/conversions/init', methods=['POST'])
def init_conversion():
    auth_err = _require_login()
    if auth_err:
        return auth_err
    data = request.get_json(silent=True) or {}
    requested_id = (data.get('conversion_id') or '').strip()
    import re
    if not requested_id or not re.fullmatch(r'[a-fA-F0-9\-]{10,80}', requested_id):
        return jsonify({'error': 'conversion_id inválido'}), 400

    filename = secure_filename(data.get('filename') or '')
    if not filename:
        filename = 'documento'
    book_title = build_book_title(data.get('book_title') or filename)
    file_type = (data.get('file_type') or '').strip().lower()
    if file_type and file_type not in ALLOWED_EXTENSIONS:
        file_type = ''

    options = data.get('options') or {}
    if not isinstance(options, dict):
        options = {}
    if 'split_mode' not in options:
        options['split_mode'] = 'chapter'

    existing = _db_get_conversion(requested_id)
    if existing:
        uid = existing.get('user_uid')
        if uid and g.firebase_user and uid != g.firebase_user.get('uid'):
            return jsonify({'error': 'Conversão não encontrada'}), 404
        return jsonify({'success': True, 'conversion_id': requested_id})

    now = datetime.now().isoformat()
    msg = 'Enviando arquivo...'
    _db_upsert_conversion(
        requested_id,
        source_filename=filename,
        source_type=file_type or None,
        book_title=book_title,
        user_uid=g.firebase_user.get('uid') if g.firebase_user else None,
        user_email=g.firebase_user.get('email') if g.firebase_user else None,
        user_name=g.firebase_user.get('name') if g.firebase_user else None,
        created_at=now,
        status='uploading',
        progress=0,
        message=msg,
        options_json=json.dumps(options, ensure_ascii=False),
        control_status='',
        client_ip=request.remote_addr,
        user_agent=request.headers.get('User-Agent')
    )
    return jsonify({'success': True, 'conversion_id': requested_id})

@app.route('/api/upload/status/<conversion_id>')
def upload_status(conversion_id):
    auth_err = _require_login()
    if auth_err:
        return auth_err
    saved = _db_get_conversion(conversion_id)
    if not saved:
        return jsonify({'error': 'Conversão não encontrada'}), 404
    uid = saved.get('user_uid')
    if uid and g.firebase_user and uid != g.firebase_user.get('uid'):
        return jsonify({'error': 'Conversão não encontrada'}), 404
    sess = _db_get_upload_session(conversion_id) or {}
    return jsonify({
        'conversion_id': conversion_id,
        'status': saved.get('status'),
        'filename': sess.get('filename') or saved.get('source_filename'),
        'total_size': int(sess.get('total_size') or 0),
        'received_size': int(sess.get('received_size') or 0)
    })

@app.route('/api/upload/chunk/<conversion_id>', methods=['POST'])
def upload_chunk(conversion_id):
    auth_err = _require_login()
    if auth_err:
        return auth_err
    try:
        saved = _db_get_conversion(conversion_id)
        if not saved:
            return jsonify({'error': 'Conversão não encontrada'}), 404
        uid = saved.get('user_uid')
        if uid and g.firebase_user and uid != g.firebase_user.get('uid'):
            return jsonify({'error': 'Conversão não encontrada'}), 404

        try:
            offset = int(request.args.get('offset', '0'))
        except Exception:
            offset = 0
        try:
            total = int(request.args.get('total', '0'))
        except Exception:
            total = 0

        chunk = request.get_data(cache=False) or b''
        if not chunk:
            return jsonify({'error': 'Chunk vazio'}), 400

        sess = _db_get_upload_session(conversion_id)
        if not sess:
            fname = saved.get('source_filename') or 'upload.bin'
            safe_fname = secure_filename(fname) or 'upload.bin'
            tmp_path = os.path.join(app.config['UPLOAD_FOLDER'], f"upload_{secure_filename(conversion_id)}_{safe_fname}.part")
            _db_upsert_upload_session(
                conversion_id,
                user_uid=g.firebase_user.get('uid') if g.firebase_user else None,
                filename=safe_fname,
                temp_path=tmp_path,
                total_size=total if total > 0 else None,
                received_size=0,
                created_at=datetime.now().isoformat()
            )
            sess = _db_get_upload_session(conversion_id)

        if sess and sess.get('user_uid') and g.firebase_user and sess.get('user_uid') != g.firebase_user.get('uid'):
            return jsonify({'error': 'Conversão não encontrada'}), 404

        temp_path = sess.get('temp_path') or ''
        received = int(sess.get('received_size') or 0)
        expected_total = int(sess.get('total_size') or 0)
        if total > 0 and expected_total != total:
            expected_total = total

        if offset != received:
            return jsonify({'ok': True, 'received_size': received, 'total_size': expected_total}), 409

        os.makedirs(os.path.dirname(temp_path), exist_ok=True)
        with open(temp_path, 'ab') as f:
            f.write(chunk)

        received += len(chunk)
        _db_upsert_upload_session(conversion_id, received_size=received, total_size=expected_total or None)
        _db_upsert_conversion(conversion_id, status='uploading', message=f'Enviando arquivo... {received}/{expected_total or 0}')
        return jsonify({'ok': True, 'received_size': received, 'total_size': expected_total})
    except Exception as e:
        try:
            import traceback
            traceback.print_exc()
        except Exception:
            pass
        return jsonify({'error': f'Erro no upload: {type(e).__name__}: {str(e)}'}), 500

@app.route('/api/upload/complete/<conversion_id>', methods=['POST'])
def upload_complete(conversion_id):
    auth_err = _require_login()
    if auth_err:
        return auth_err
    saved = _db_get_conversion(conversion_id)
    if not saved:
        return jsonify({'error': 'Conversão não encontrada'}), 404
    uid = saved.get('user_uid')
    if uid and g.firebase_user and uid != g.firebase_user.get('uid'):
        return jsonify({'error': 'Conversão não encontrada'}), 404

    sess = _db_get_upload_session(conversion_id)
    if not sess:
        return jsonify({'error': 'Sessão de upload não encontrada'}), 404
    if sess.get('user_uid') and g.firebase_user and sess.get('user_uid') != g.firebase_user.get('uid'):
        return jsonify({'error': 'Conversão não encontrada'}), 404

    temp_path = sess.get('temp_path') or ''
    total = int(sess.get('total_size') or 0)
    received = int(sess.get('received_size') or 0)
    if total and received != total:
        return jsonify({'error': f'Upload incompleto ({received}/{total})'}), 400
    if not temp_path or not os.path.exists(temp_path):
        return jsonify({'error': 'Arquivo temporário não encontrado'}), 404

    filename = sess.get('filename') or saved.get('source_filename') or 'documento'
    filename = secure_filename(filename) or 'documento'
    book_title = saved.get('book_title') or build_book_title(filename)
    pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{conversion_id}_{filename}")
    try:
        os.replace(temp_path, pdf_path)
    except Exception as e:
        return jsonify({'error': f'Erro ao finalizar upload: {str(e)}'}), 500

    _db_delete_upload_session(conversion_id)
    options = saved.get('options') or {}
    if not isinstance(options, dict):
        options = {}
    if 'file_type' not in options:
        try:
            options['file_type'] = filename.rsplit('.', 1)[1].lower()
        except Exception:
            options['file_type'] = 'pdf'

    src_remote = _storage_upload(
        pdf_path,
        f"uploads/{conversion_id}/{filename}",
        content_type=mimetypes.guess_type(filename)[0] or 'application/octet-stream'
    )
    _start_conversion_processing(conversion_id, pdf_path, filename, book_title, options, src_remote=src_remote)
    return jsonify({'ok': True, 'conversion_id': conversion_id})

def process_pdf(conversion_id, pdf_path, options=None):
    """Process file with caching and advanced options"""
    if options is None:
        options = {'lang': 'pt', 'speed': 1.0, 'voice_type': 'default', 'enhanced_voice': 'default', 'file_type': 'pdf', 'split_mode': 'chapter'}
    
    try:
        # Get file hash for caching
        file_hash = get_file_hash(pdf_path)
        file_type = options.get('file_type', 'pdf')
        
        # Check cache first
        cache_result = check_cache(file_hash, options)
        if cache_result:
            processing_status[conversion_id]['status'] = 'completed'
            processing_status[conversion_id]['progress'] = 100
            processing_status[conversion_id]['message'] = 'Conversão recuperada do cache!'
            processing_status[conversion_id]['audio_files'] = cache_result['audio_files']
            processing_status[conversion_id]['pages_info'] = cache_result['pages_info']
            processing_status[conversion_id]['chapters_info'] = cache_result.get('chapters_info', [])
            processing_status[conversion_id]['total_chunks'] = len(cache_result['audio_files'])
            processing_status[conversion_id]['from_cache'] = True

            _db_upsert_conversion(
                conversion_id,
                status='completed',
                progress=100,
                message='Conversão recuperada do cache!',
                from_cache=1,
                options_json=json.dumps(options, ensure_ascii=False),
                chapters_json=json.dumps(cache_result.get('chapters_info', []), ensure_ascii=False)
            )
            for p in cache_result.get('pages_info', []):
                _db_upsert_page(
                    conversion_id,
                    p.get('page_number'),
                    p.get('filename'),
                    p.get('full_path'),
                    0,
                    text=p.get('text') or None,
                    display_label=p.get('display_label') or None
                )
            
            # Clean up uploaded file
            try:
                os.remove(pdf_path)
            except:
                pass
            return
        
        # Update status
        processing_status[conversion_id]['status'] = 'processing'
        processing_status[conversion_id]['progress'] = 10
        processing_status[conversion_id]['message'] = f'Extraindo texto do arquivo {file_type.upper()}...'
        _db_upsert_conversion(
            conversion_id,
            status='processing',
            progress=int(processing_status[conversion_id]['progress']),
            message=processing_status[conversion_id]['message'],
            options_json=json.dumps(options, ensure_ascii=False)
        )
        
        # Extract text page by page
        pages_data = extract_text_from_file(pdf_path, file_type, options=options)
        
        if not pages_data:
            processing_status[conversion_id]['status'] = 'error'
            processing_status[conversion_id]['message'] = 'Não foi possível extrair texto do arquivo'
            return
        
        header_set, footer_set = detect_common_headers_footers(pages_data)
        for p in pages_data:
            try:
                p['text'] = strip_headers_footers(p.get('text', ''), header_set, footer_set)
            except Exception:
                pass

        total_pages = len(pages_data)
        processing_status[conversion_id]['total_pages'] = total_pages
        split_mode = options.get('split_mode', 'chapter')
        if split_mode not in ('page', 'chapter'):
            split_mode = 'chapter'
        processing_status[conversion_id]['message'] = f'Arquivo com {total_pages} páginas. Convertendo...'
        _db_upsert_conversion(
            conversion_id,
            status='processing',
            progress=int(processing_status[conversion_id]['progress']),
            message=processing_status[conversion_id]['message']
        )
        
        # Convert to audio
        book_title = None
        if conversion_id in processing_status:
            book_title = processing_status[conversion_id].get('book_title')
        if not book_title:
            book_title = build_book_title(os.path.basename(pdf_path))
        audio_output_dir = os.path.join(app.config['AUDIO_FOLDER'], conversion_id)
        audio_files = []
        chapters_info = []
        existing_pages = _db_get_pages_map(conversion_id)

        if split_mode == 'chapter':
            chapters = detect_chapters_from_pages(pages_data)
            if not chapters:
                chapters = [{'chapter_index': 1, 'title': 'Conteúdo', 'text': '\n\n'.join([p.get('text', '') for p in pages_data if p.get('text')])}]

            unit_items = []
            seq = 0
            total_units = 0
            chapters_info = []
            for ch in chapters:
                ch_text = clean_text_for_tts(ch.get('text', ''))
                parts = split_text_chunks(ch_text, max_chars=1800)
                if not parts:
                    continue
                chapters_info.append({'chapter_index': ch.get('chapter_index'), 'title': ch.get('title'), 'parts': len(parts)})
                total_units += len(parts)

            total_units = max(1, int(total_units))

            for ch in chapters:
                ch_text = clean_text_for_tts(ch.get('text', ''))
                parts = split_text_chunks(ch_text, max_chars=1800)
                if not parts:
                    continue
                for part_i, part_text in enumerate(parts, start=1):
                    ctrl = _get_control_status(conversion_id)
                    if ctrl == 'cancel':
                        processing_status[conversion_id]['status'] = 'cancelled'
                        processing_status[conversion_id]['message'] = 'Conversão cancelada.'
                        _db_upsert_conversion(
                            conversion_id,
                            status='cancelled',
                            message=processing_status[conversion_id]['message'],
                            control_status='cancel',
                            progress=int(processing_status[conversion_id].get('progress') or 0)
                        )
                        return
                    if ctrl == 'pause':
                        processing_status[conversion_id]['status'] = 'paused'
                        processing_status[conversion_id]['message'] = 'Conversão pausada.'
                        _db_upsert_conversion(
                            conversion_id,
                            status='paused',
                            message=processing_status[conversion_id]['message'],
                            control_status='pause',
                            progress=int(processing_status[conversion_id].get('progress') or 0)
                        )
                        return
                    seq += 1
                    filename = f"capitulo_{int(ch.get('chapter_index') or 1):02d}_parte_{part_i:02d}.mp3"
                    out_path = os.path.join(audio_output_dir, filename)
                    progress = int(20 + (75 * (seq / total_units)))
                    processing_status[conversion_id]['progress'] = min(99, max(0, progress))
                    if os.path.exists(out_path):
                        display = f"{ch.get('title')} — Parte {part_i}"
                        unit_items.append({
                            'page_number': seq,
                            'filename': os.path.basename(out_path),
                            'full_path': out_path,
                            'storage': None,
                            'display_label': display,
                            'chapter_index': ch.get('chapter_index'),
                            'chapter_title': ch.get('title'),
                            'part_index': part_i,
                            'part_count': len(parts)
                        })
                        _db_upsert_page(
                            conversion_id,
                            seq,
                            os.path.basename(out_path),
                            out_path,
                            len(part_text or ''),
                            text=part_text,
                            display_label=display
                        )
                        continue
                    processing_status[conversion_id]['message'] = f'Convertendo {ch.get("title")} (parte {part_i}/{len(parts)})...'
                    _db_upsert_conversion(
                        conversion_id,
                        status='processing',
                        progress=int(processing_status[conversion_id]['progress']),
                        message=processing_status[conversion_id]['message']
                    )
                    tts_res = tts_to_file_with_alignment(
                        part_text,
                        out_path,
                        lang=options['lang'],
                        speed=options['speed'],
                        voice_type=options['voice_type'],
                        enhanced_voice=options.get('enhanced_voice', 'default'),
                        tts_engine=options.get('tts_engine', 'gtts'),
                        tts_voice=options.get('tts_voice') or None,
                        sapi_voice=options.get('sapi_voice', ''),
                        use_offline=bool(options.get('use_offline', False)),
                        normalize_audio=bool(options.get('normalize_audio', False)),
                        trim_silence=bool(options.get('trim_silence', False))
                    )
                    audio_file = tts_res.get('path')
                    alignment = tts_res.get('alignment')
                    if audio_file:
                        audio_remote = _storage_upload(
                            audio_file,
                            f"audio/{conversion_id}/{os.path.basename(audio_file)}",
                            content_type='audio/mpeg'
                        )
                        display = f"{ch.get('title')} — Parte {part_i}"
                        unit_items.append({
                            'page_number': seq,
                            'filename': os.path.basename(audio_file),
                            'full_path': audio_file,
                            'storage': audio_remote,
                            'display_label': display,
                            'chapter_index': ch.get('chapter_index'),
                            'chapter_title': ch.get('title'),
                            'part_index': part_i,
                            'part_count': len(parts)
                        })
                        _db_upsert_page(
                            conversion_id,
                            seq,
                            os.path.basename(audio_file),
                            audio_file,
                            len(part_text or ''),
                            text=part_text,
                            display_label=display,
                            alignment=alignment
                        )
                    else:
                        pass

            audio_files = unit_items
        else:
        
            for i, page_data in enumerate(pages_data):
                ctrl = _get_control_status(conversion_id)
                if ctrl == 'cancel':
                    processing_status[conversion_id]['status'] = 'cancelled'
                    processing_status[conversion_id]['message'] = 'Conversão cancelada.'
                    _db_upsert_conversion(
                        conversion_id,
                        status='cancelled',
                        message=processing_status[conversion_id]['message'],
                        control_status='cancel',
                        progress=int(processing_status[conversion_id].get('progress') or 0)
                    )
                    return
                if ctrl == 'pause':
                    processing_status[conversion_id]['status'] = 'paused'
                    processing_status[conversion_id]['message'] = 'Conversão pausada.'
                    _db_upsert_conversion(
                        conversion_id,
                        status='paused',
                        message=processing_status[conversion_id]['message'],
                        control_status='pause',
                        progress=int(processing_status[conversion_id].get('progress') or 0)
                    )
                    return
                page_number = page_data['page_number']
                page_text = page_data['text']
                page_progress = int(20 + (75 * (i + 1) / max(1, total_pages)))
                processing_status[conversion_id]['progress'] = min(99, max(0, page_progress))
                processing_status[conversion_id]['message'] = f'Convertendo página {page_number}/{total_pages} ({options["lang"]})...'
                _db_upsert_conversion(
                    conversion_id,
                    status='processing',
                    progress=int(processing_status[conversion_id]['progress']),
                    message=processing_status[conversion_id]['message']
                )
                prev = existing_pages.get(int(page_number))
                if prev:
                    resolved = _resolve_audio_path(conversion_id, prev.get('full_path'), filename=prev.get('filename'))
                    if resolved and os.path.exists(resolved):
                        audio_files.append({
                            'page_number': page_number,
                            'filename': prev.get('filename') or os.path.basename(resolved),
                            'full_path': resolved,
                            'storage': None,
                            'display_label': prev.get('display_label')
                        })
                        continue
            
                # Convert this page to audio with options
                audio_file = text_to_speech_page(
                    page_text, 
                    audio_output_dir, 
                    page_number, 
                    lang=options['lang'],
                    speed=options['speed'],
                    voice_type=options['voice_type'],
                    enhanced_voice=options.get('enhanced_voice', 'default'),
                    tts_engine=options.get('tts_engine', 'gtts'),
                    tts_voice=options.get('tts_voice') or None,
                    sapi_voice=options.get('sapi_voice', ''),
                    use_offline=bool(options.get('use_offline', False))
                )
            
                if audio_file:
                    audio_remote = _storage_upload(
                        audio_file,
                        f"audio/{conversion_id}/{os.path.basename(audio_file)}",
                        content_type='audio/mpeg' if audio_file.lower().endswith('.mp3') else 'audio/wav'
                    )
                    audio_files.append({
                        'page_number': page_number,
                        'filename': os.path.basename(audio_file),
                        'full_path': audio_file,
                        'storage': audio_remote
                    })
                    print(f"Página {page_number} convertida com sucesso: {audio_file}")
                    _db_upsert_page(
                        conversion_id,
                        page_number,
                        os.path.basename(audio_file),
                        audio_file,
                        len(page_text or ''),
                        text=page_text,
                        display_label=None
                    )
                    if FIRESTORE_CLIENT is not None and audio_remote:
                        try:
                            doc_id = str(int(page_number))
                            FIRESTORE_CLIENT.collection('conversions').document(conversion_id).collection('pages').document(doc_id).set(
                                {'storage': audio_remote},
                                merge=True
                            )
                        except Exception:
                            pass
                else:
                    print(f"Pulando página {page_number} - sem texto ou erro na conversão")
        
        if not audio_files:
            processing_status[conversion_id]['status'] = 'error'
            processing_status[conversion_id]['message'] = 'Não foi possível converter nenhuma página'
            return
        
        # Sort files by page number
        audio_files.sort(key=lambda x: x['page_number'])

        processing_status[conversion_id]['progress'] = 99
        processing_status[conversion_id]['message'] = 'Finalizando...'
        _db_upsert_conversion(
            conversion_id,
            status='processing',
            progress=int(processing_status[conversion_id]['progress']),
            message=processing_status[conversion_id]['message']
        )
        
        # Prepare result data
        result_data = {
            'audio_files': [item['full_path'] for item in audio_files],
            'pages_info': audio_files,
            'chapters_info': chapters_info,
            'options': options,
            'file_hash': file_hash
        }
        
        # Save to cache
        save_to_cache(file_hash, options, result_data)
        
        # Update status with completion
        processing_status[conversion_id]['status'] = 'completed'
        processing_status[conversion_id]['progress'] = 100
        if split_mode == 'chapter':
            processing_status[conversion_id]['message'] = f'Conversão concluída! {len(audio_files)} partes por capítulo geradas.'
        else:
            processing_status[conversion_id]['message'] = f'Conversão concluída! {len(audio_files)} páginas convertidas.'
        processing_status[conversion_id]['audio_files'] = result_data['audio_files']
        processing_status[conversion_id]['pages_info'] = result_data['pages_info']
        processing_status[conversion_id]['chapters_info'] = result_data.get('chapters_info', [])
        processing_status[conversion_id]['total_chunks'] = len(audio_files)
        processing_status[conversion_id]['options'] = options

        _db_upsert_conversion(
            conversion_id,
            status='completed',
            progress=100,
            message=processing_status[conversion_id]['message'],
            options_json=json.dumps(options, ensure_ascii=False),
            chapters_json=json.dumps(result_data.get('chapters_info', []), ensure_ascii=False),
            from_cache=1 if processing_status[conversion_id].get('from_cache') else 0
        )
        
        # Clean up uploaded file
        try:
            os.remove(pdf_path)
        except:
            pass
            
    except Exception as e:
        processing_status[conversion_id]['status'] = 'error'
        processing_status[conversion_id]['message'] = f'Erro no processamento: {str(e)}'
        processing_status[conversion_id]['progress'] = 0
        _db_upsert_conversion(
            conversion_id,
            status='error',
            progress=0,
            message=processing_status[conversion_id]['message']
        )

@app.route('/status/<conversion_id>')
def get_status(conversion_id):
    auth_err = _require_login()
    if auth_err:
        return auth_err
    if conversion_id in processing_status:
        status = processing_status[conversion_id]
        uid = status.get('user_uid')
        if uid and g.firebase_user and uid != g.firebase_user.get('uid'):
            return jsonify({'error': 'Conversão não encontrada'}), 404
        return jsonify(status)

    saved = _db_get_conversion(conversion_id)
    if not saved:
        return jsonify({'error': 'Conversão não encontrada'}), 404
    uid = saved.get('user_uid')
    if uid and g.firebase_user and uid != g.firebase_user.get('uid'):
        return jsonify({'error': 'Conversão não encontrada'}), 404
    try:
        st = (saved.get('status') or '').strip().lower()
        cs = (saved.get('control_status') or '').strip().lower()
        path = saved.get('source_local_path') or ''
        if st == 'queued' and conversion_id not in processing_status and cs not in ('pause', 'cancel'):
            if not path or not os.path.exists(path):
                _db_upsert_conversion(conversion_id, status='error', message='Arquivo original não encontrado no servidor.')
                saved = _db_get_conversion(conversion_id) or saved
            else:
                try:
                    job = _db_get_job(conversion_id) or {}
                    jst = (job.get('status') or '').strip().lower()
                    if jst not in ('queued', 'running'):
                        _db_upsert_job(conversion_id, status='queued', attempts=int(job.get('attempts') or 0), last_error=None)
                    _start_job_worker()
                except Exception:
                    pass
        if st == 'processing' and conversion_id not in processing_status and cs not in ('pause', 'cancel'):
            if path and os.path.exists(path):
                options = saved.get('options') or {}
                if not isinstance(options, dict):
                    options = {}
                processing_status[conversion_id] = {
                    'status': 'queued',
                    'progress': int(saved.get('progress') or 0),
                    'message': 'Na fila para retomar...',
                    'filename': saved.get('source_filename'),
                    'book_title': saved.get('book_title'),
                    'created_at': saved.get('created_at') or datetime.now().isoformat(),
                    'options': options,
                    'user_uid': uid,
                    'source_local_path': path,
                    'control_status': ''
                }
                _db_upsert_conversion(conversion_id, status='queued', message='Na fila para retomar...', control_status='')
                _db_upsert_job(conversion_id, status='queued', attempts=0, last_error=None)
                saved = _db_get_conversion(conversion_id) or saved
    except Exception:
        pass
    return jsonify(saved)

@app.route('/api/conversions')
def list_conversions():
    auth_err = _require_login()
    if auth_err:
        return auth_err
    limit = request.args.get('limit', '50')
    offset = request.args.get('offset', '0')
    try:
        limit_i = max(1, min(200, int(limit)))
    except Exception:
        limit_i = 50
    try:
        offset_i = max(0, int(offset))
    except Exception:
        offset_i = 0

    if FIRESTORE_CLIENT is not None:
        q = FIRESTORE_CLIENT.collection('conversions').order_by('created_at', direction=firebase_firestore.Query.DESCENDING)
        uid = g.firebase_user.get('uid') if g.firebase_user else None
        if uid:
            q = q.where('user_uid', '==', uid)
        if offset_i:
            q = q.offset(offset_i)
        docs = q.limit(limit_i).stream()
        items = []
        for doc in docs:
            d = doc.to_dict() or {}
            d['conversion_id'] = d.get('conversion_id') or doc.id
            items.append({
                'conversion_id': d.get('conversion_id'),
                'source_filename': d.get('source_filename'),
                'source_type': d.get('source_type'),
                'book_title': d.get('book_title'),
                'created_at': d.get('created_at'),
                'updated_at': d.get('updated_at'),
                'status': d.get('status'),
                'progress': d.get('progress'),
                'message': d.get('message'),
                'from_cache': d.get('from_cache', 0),
                'from_edited_text': d.get('from_edited_text', 0),
                'merged_file': d.get('merged_file'),
                'merge_status': d.get('merge_status'),
                'merge_progress': d.get('merge_progress'),
                'merge_message': d.get('merge_message')
            })
        return jsonify({'items': items, 'limit': limit_i, 'offset': offset_i})

    uid = g.firebase_user.get('uid') if g.firebase_user else None
    with DB_LOCK:
        conn = _db_connect()
        try:
            where_sql = ''
            params = []
            if uid:
                where_sql = f'WHERE user_uid={_ph()}'
                params.append(uid)
            rows = conn.execute(
                '''
                SELECT conversion_id, source_filename, source_type, book_title, created_at, updated_at,
                       status, progress, message, from_cache, from_edited_text,
                       merged_file, merge_status, merge_progress, merge_message
                FROM conversions
                ''' + where_sql + '''
                ORDER BY created_at DESC
                LIMIT ''' + _ph() + ' OFFSET ' + _ph() + '''
                ''',
                (*params, limit_i, offset_i)
            ).fetchall()
            result = [dict(r) for r in rows]
        finally:
            conn.close()
    return jsonify({'items': result, 'limit': limit_i, 'offset': offset_i})

@app.route('/api/conversions/<conversion_id>')
def get_conversion_saved(conversion_id):
    auth_err = _require_login()
    if auth_err:
        return auth_err
    saved = _db_get_conversion(conversion_id)
    if not saved:
        return jsonify({'error': 'Conversão não encontrada'}), 404
    uid = saved.get('user_uid')
    if uid and g.firebase_user and uid != g.firebase_user.get('uid'):
        return jsonify({'error': 'Conversão não encontrada'}), 404
    return jsonify(saved)

def _share_is_active(conv):
    if not conv:
        return False
    if int(conv.get('share_enabled') or 0) != 1:
        return False
    token = (conv.get('share_token') or '').strip()
    if not token:
        return False
    exp = (conv.get('share_expires_at') or '').strip()
    if exp:
        try:
            if datetime.fromisoformat(exp) <= datetime.now():
                return False
        except Exception:
            pass
    return True

@app.route('/api/conversions/<conversion_id>/share', methods=['GET', 'POST'])
def share_conversion(conversion_id):
    auth_err = _require_login()
    if auth_err:
        return auth_err
    saved = _db_get_conversion(conversion_id)
    if not saved:
        return jsonify({'error': 'Conversão não encontrada'}), 404
    uid = saved.get('user_uid')
    if uid and g.firebase_user and uid != g.firebase_user.get('uid'):
        return jsonify({'error': 'Conversão não encontrada'}), 404

    if request.method == 'GET':
        token = saved.get('share_token')
        enabled = int(saved.get('share_enabled') or 0)
        exp = saved.get('share_expires_at')
        share_url = None
        if token and enabled == 1:
            share_url = request.host_url.rstrip('/') + f"/s/{token}"
        return jsonify({'share_enabled': enabled == 1, 'share_url': share_url, 'share_expires_at': exp})

    data = request.get_json(silent=True) or {}
    try:
        expires_days = int(data.get('expires_days') or 0)
    except Exception:
        expires_days = 0
    if expires_days < 0:
        expires_days = 0
    if expires_days > 365:
        expires_days = 365

    token = secrets.token_urlsafe(24)
    exp = None
    if expires_days:
        exp = (datetime.now() + timedelta(days=expires_days)).isoformat()

    _db_upsert_conversion(
        conversion_id,
        share_token=token,
        share_enabled=1,
        share_expires_at=exp
    )
    share_url = request.host_url.rstrip('/') + f"/s/{token}"
    return jsonify({'share_enabled': True, 'share_url': share_url, 'share_expires_at': exp})

@app.route('/api/conversions/<conversion_id>/share/revoke', methods=['POST'])
def revoke_share_conversion(conversion_id):
    auth_err = _require_login()
    if auth_err:
        return auth_err
    saved = _db_get_conversion(conversion_id)
    if not saved:
        return jsonify({'error': 'Conversão não encontrada'}), 404
    uid = saved.get('user_uid')
    if uid and g.firebase_user and uid != g.firebase_user.get('uid'):
        return jsonify({'error': 'Conversão não encontrada'}), 404
    _db_upsert_conversion(conversion_id, share_enabled=0, share_token=None, share_expires_at=None)
    return jsonify({'share_enabled': False})

@app.route('/s/<share_token>')
def share_page(share_token):
    conv = _db_get_conversion_by_share_token(share_token)
    if not _share_is_active(conv):
        return render_template('share.html', not_found=True), 404
    title = conv.get('book_title') or conv.get('source_filename') or 'Audiolivro'
    try:
        app.jinja_env.cache.clear()
    except Exception:
        pass
    return render_template('share.html', not_found=False, share_token=share_token, title=title)

@app.route('/s/<share_token>/data')
def share_data(share_token):
    conv = _db_get_conversion_by_share_token(share_token)
    if not _share_is_active(conv):
        return jsonify({'error': 'Link inválido ou expirado'}), 404
    if (conv.get('status') or '') not in ('completed', 'processing', 'paused'):
        pass
    items = []
    for p in (conv.get('pages_info') or []):
        items.append({
            'page_number': p.get('page_number'),
            'filename': p.get('filename'),
            'display_label': p.get('display_label')
        })
    merged_name = None
    merged_file = conv.get('merged_file')
    if merged_file:
        try:
            merged_name = os.path.basename(str(merged_file))
        except Exception:
            merged_name = None
    base = f"/s/{share_token}"
    m4b_url = None
    try:
        _configure_ffmpeg()
        if FFMPEG_AVAILABLE and conv.get('merged_file') and os.path.exists(conv.get('merged_file')):
            m4b_url = base + "/m4b"
    except Exception:
        m4b_url = None
    return jsonify({
        'title': conv.get('book_title') or conv.get('source_filename') or 'Audiolivro',
        'status': conv.get('status'),
        'items': items,
        'zip_url': base + '/zip',
        'merged': bool(merged_name),
        'merged_url': (base + f"/merged/{secure_filename(merged_name)}") if merged_name else None,
        'm4b_url': m4b_url
    })

@app.route('/s/<share_token>/play/<filename>')
def share_play(share_token, filename):
    conv = _db_get_conversion_by_share_token(share_token)
    if not _share_is_active(conv):
        return jsonify({'error': 'Link inválido ou expirado'}), 404
    cid = conv.get('conversion_id')
    safe_name = secure_filename(filename)
    audio_path = _resolve_audio_path(cid, None, filename=filename)
    if (not audio_path or not os.path.exists(audio_path)) and cid:
        saved = _db_get_conversion(cid) or {}
        page = _db_get_page_by_filename(cid, safe_name) or {}
        text = (page.get('text') or '').strip()
        options = saved.get('options') if isinstance(saved.get('options'), dict) else {}
        if text:
            out_dir = os.path.join(app.config['AUDIO_FOLDER'], secure_filename(cid))
            out_path = os.path.join(out_dir, safe_name)
            res = tts_to_file_with_alignment(
                text,
                out_path,
                lang=str(options.get('lang') or 'pt'),
                speed=float(options.get('speed') or 1.0),
                voice_type=str(options.get('voice_type') or 'default'),
                enhanced_voice=str(options.get('enhanced_voice') or 'default'),
                tts_engine=str(options.get('tts_engine') or 'gtts'),
                tts_voice=(options.get('tts_voice') or None),
                sapi_voice=str(options.get('sapi_voice') or ''),
                use_offline=bool(options.get('use_offline', False)),
                normalize_audio=bool(options.get('normalize_audio', False)),
                trim_silence=bool(options.get('trim_silence', False))
            )
            audio_path = res.get('path') or audio_path
            if audio_path and os.path.exists(audio_path):
                try:
                    _db_update_page_full_path(cid, safe_name, audio_path)
                except Exception:
                    pass
    if not audio_path or not os.path.exists(audio_path):
        return jsonify({'error': 'Arquivo de áudio não encontrado'}), 404
    resp = send_file(audio_path, conditional=False)
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

@app.route('/s/<share_token>/download/<filename>')
def share_download(share_token, filename):
    conv = _db_get_conversion_by_share_token(share_token)
    if not _share_is_active(conv):
        return jsonify({'error': 'Link inválido ou expirado'}), 404
    cid = conv.get('conversion_id')
    safe_name = secure_filename(filename)
    audio_path = _resolve_audio_path(cid, None, filename=filename)
    if (not audio_path or not os.path.exists(audio_path)) and cid:
        saved = _db_get_conversion(cid) or {}
        page = _db_get_page_by_filename(cid, safe_name) or {}
        text = (page.get('text') or '').strip()
        options = saved.get('options') if isinstance(saved.get('options'), dict) else {}
        if text:
            out_dir = os.path.join(app.config['AUDIO_FOLDER'], secure_filename(cid))
            out_path = os.path.join(out_dir, safe_name)
            res = tts_to_file_with_alignment(
                text,
                out_path,
                lang=str(options.get('lang') or 'pt'),
                speed=float(options.get('speed') or 1.0),
                voice_type=str(options.get('voice_type') or 'default'),
                enhanced_voice=str(options.get('enhanced_voice') or 'default'),
                tts_engine=str(options.get('tts_engine') or 'gtts'),
                tts_voice=(options.get('tts_voice') or None),
                sapi_voice=str(options.get('sapi_voice') or ''),
                use_offline=bool(options.get('use_offline', False)),
                normalize_audio=bool(options.get('normalize_audio', False)),
                trim_silence=bool(options.get('trim_silence', False))
            )
            audio_path = res.get('path') or audio_path
            if audio_path and os.path.exists(audio_path):
                try:
                    _db_update_page_full_path(cid, safe_name, audio_path)
                except Exception:
                    pass
    if not audio_path or not os.path.exists(audio_path):
        return jsonify({'error': 'Arquivo de áudio não encontrado'}), 404
    resp = send_file(audio_path, as_attachment=True, download_name=safe_name, conditional=False)
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

@app.route('/s/<share_token>/merged/<filename>')
def share_download_merged(share_token, filename):
    conv = _db_get_conversion_by_share_token(share_token)
    if not _share_is_active(conv):
        return jsonify({'error': 'Link inválido ou expirado'}), 404
    merged_file = conv.get('merged_file')
    if not merged_file or not os.path.exists(merged_file):
        return jsonify({'error': 'Arquivo mesclado não encontrado'}), 404
    safe_name = secure_filename(filename) or 'audiolivro.mp3'
    resp = send_file(merged_file, as_attachment=True, download_name=safe_name, conditional=False)
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

@app.route('/s/<share_token>/zip')
def share_download_zip(share_token):
    conv = _db_get_conversion_by_share_token(share_token)
    if not _share_is_active(conv):
        return jsonify({'error': 'Link inválido ou expirado'}), 404

    book_title = conv.get('book_title') or conv.get('source_filename') or f"audiobook_{conv.get('conversion_id')}"
    book_title = build_book_title(book_title)
    zip_name = f"{book_title}_audios.zip"

    pages_info = conv.get('pages_info', []) or []
    files = []
    for p in pages_info:
        resolved = _resolve_audio_path(conv.get('conversion_id'), p.get('full_path'), filename=p.get('filename'))
        if resolved:
            arc = os.path.basename(resolved)
            label = (p.get('display_label') or '').strip()
            folder = ''
            if label:
                if '—' in label:
                    folder = label.split('—', 1)[0].strip()
                else:
                    folder = label.strip()
            folder = secure_filename(folder) if folder else ''
            if folder:
                arc = f"{folder}/{arc}"
            files.append((resolved, arc))

    merged_file = conv.get('merged_file')
    if merged_file and os.path.exists(merged_file):
        files.append((merged_file, os.path.basename(merged_file)))

    if not files:
        return jsonify({'error': 'Nenhum arquivo local encontrado para compactar'}), 404

    tmp = tempfile.NamedTemporaryFile(prefix=f"{secure_filename(conv.get('conversion_id') or 'share')}_", suffix=".zip", delete=False)
    tmp_path = tmp.name
    tmp.close()

    try:
        with zipfile.ZipFile(tmp_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            added = set()
            for full_path, arcname in files:
                if arcname in added:
                    base, ext = os.path.splitext(arcname)
                    i = 2
                    while f"{base}_{i}{ext}" in added:
                        i += 1
                    arcname = f"{base}_{i}{ext}"
                zf.write(full_path, arcname)
                added.add(arcname)
    except Exception as e:
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        return jsonify({'error': f'Erro ao gerar ZIP: {str(e)}'}), 500

    @after_this_request
    def _cleanup_zip(resp):
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        return resp

    resp = send_file(tmp_path, as_attachment=True, download_name=zip_name, conditional=False)
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

@app.route('/s/<share_token>/m4b')
def share_download_m4b(share_token):
    conv = _db_get_conversion_by_share_token(share_token)
    if not _share_is_active(conv):
        return jsonify({'error': 'Link inválido ou expirado'}), 404
    _configure_ffmpeg()
    if not FFMPEG_AVAILABLE:
        return jsonify({'error': 'FFmpeg não encontrado'}), 500
    merged_file = conv.get('merged_file')
    if not merged_file or not os.path.exists(merged_file):
        return jsonify({'error': 'Arquivo mesclado não encontrado'}), 404
    book_title = conv.get('book_title') or conv.get('source_filename') or f"audiobook_{conv.get('conversion_id')}"
    book_title = build_book_title(book_title)
    filename = f"{book_title}.m4b"
    tmp = tempfile.NamedTemporaryFile(prefix=f"{secure_filename(conv.get('conversion_id') or 'share')}_", suffix=".m4b", delete=False)
    out_path = tmp.name
    tmp.close()
    ff = FFMPEG_PATH or 'ffmpeg'
    cmd = [
        ff, '-y',
        '-i', merged_file,
        '-vn',
        '-c:a', 'aac',
        '-b:a', '128k',
        '-movflags', '+faststart',
        out_path
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except Exception:
        try:
            os.remove(out_path)
        except Exception:
            pass
        return jsonify({'error': 'Erro ao gerar M4B via FFmpeg'}), 500

    @after_this_request
    def _cleanup(resp):
        try:
            os.remove(out_path)
        except Exception:
            pass
        return resp

    resp = send_file(out_path, as_attachment=True, download_name=filename, conditional=False)
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

@app.route('/api/conversions/<conversion_id>/pause', methods=['POST'])
def pause_conversion(conversion_id):
    auth_err = _require_login()
    if auth_err:
        return auth_err
    saved = _db_get_conversion(conversion_id)
    if not saved:
        return jsonify({'error': 'Conversão não encontrada'}), 404
    uid = saved.get('user_uid')
    if uid and g.firebase_user and uid != g.firebase_user.get('uid'):
        return jsonify({'error': 'Conversão não encontrada'}), 404
    st = processing_status.get(conversion_id)
    if not st:
        return jsonify({'error': 'Conversão não está ativa neste servidor'}), 400
    if st.get('status') != 'processing':
        return jsonify({'error': 'Conversão não está em processamento'}), 400
    _set_control_status(conversion_id, 'pause')
    st['message'] = 'Pausando...'
    _db_upsert_conversion(conversion_id, control_status='pause', message=st.get('message'))
    return jsonify({'success': True})

@app.route('/api/conversions/<conversion_id>/cancel', methods=['POST'])
def cancel_conversion(conversion_id):
    auth_err = _require_login()
    if auth_err:
        return auth_err
    saved = _db_get_conversion(conversion_id)
    if not saved:
        return jsonify({'error': 'Conversão não encontrada'}), 404
    uid = saved.get('user_uid')
    if uid and g.firebase_user and uid != g.firebase_user.get('uid'):
        return jsonify({'error': 'Conversão não encontrada'}), 404
    st = processing_status.get(conversion_id)
    if not st:
        _db_upsert_conversion(conversion_id, status='cancelled', control_status='cancel', message='Cancelado')
        return jsonify({'success': True})
    _set_control_status(conversion_id, 'cancel')
    st['message'] = 'Cancelando...'
    _db_upsert_conversion(conversion_id, control_status='cancel', message=st.get('message'))
    return jsonify({'success': True})

@app.route('/api/conversions/<conversion_id>/resume', methods=['POST'])
def resume_conversion(conversion_id):
    auth_err = _require_login()
    if auth_err:
        return auth_err
    saved = _db_get_conversion(conversion_id)
    if not saved:
        return jsonify({'error': 'Conversão não encontrada'}), 404
    uid = saved.get('user_uid')
    if uid and g.firebase_user and uid != g.firebase_user.get('uid'):
        return jsonify({'error': 'Conversão não encontrada'}), 404

    st = processing_status.get(conversion_id)
    if st and st.get('status') == 'processing':
        return jsonify({'error': 'Conversão já está em processamento'}), 400

    options = (saved.get('options') or {})
    source_local_path = saved.get('source_local_path') or ''
    if not source_local_path or not os.path.exists(source_local_path):
        return jsonify({'error': 'Arquivo original não encontrado para retomar'}), 400

    processing_status[conversion_id] = {
        'status': 'queued',
        'progress': int(saved.get('progress') or 0),
        'message': 'Na fila para retomar...',
        'filename': saved.get('source_filename'),
        'book_title': saved.get('book_title'),
        'created_at': saved.get('created_at') or datetime.now().isoformat(),
        'options': options,
        'user_uid': saved.get('user_uid'),
        'source_local_path': source_local_path,
        'control_status': ''
    }
    _db_upsert_conversion(conversion_id, status='queued', control_status='', message='Na fila para retomar...')
    _db_upsert_job(conversion_id, status='queued', attempts=0, last_error=None)
    return jsonify({'success': True})

@app.route('/api/conversions/<conversion_id>/chapters', methods=['GET', 'POST'])
def chapters_conversion(conversion_id):
    auth_err = _require_login()
    if auth_err:
        return auth_err
    saved = _db_get_conversion(conversion_id)
    if not saved:
        return jsonify({'error': 'Conversão não encontrada'}), 404
    uid = saved.get('user_uid')
    if uid and g.firebase_user and uid != g.firebase_user.get('uid'):
        return jsonify({'error': 'Conversão não encontrada'}), 404

    if request.method == 'GET':
        return jsonify({'chapters_info': saved.get('chapters_info') or []})

    data = request.get_json(silent=True) or {}
    chapters_info = data.get('chapters_info') or []
    if not isinstance(chapters_info, list):
        return jsonify({'error': 'chapters_info inválido'}), 400
    cleaned = []
    for c in chapters_info:
        if not isinstance(c, dict):
            continue
        ci = c.get('chapter_index')
        title = (c.get('title') or '').strip()
        try:
            ci = int(ci)
        except Exception:
            continue
        if not title:
            continue
        cleaned.append({'chapter_index': ci, 'title': title, 'parts': c.get('parts')})
    cleaned.sort(key=lambda x: x.get('chapter_index') or 0)
    _db_upsert_conversion(conversion_id, chapters_json=json.dumps(cleaned, ensure_ascii=False))
    if conversion_id in processing_status:
        processing_status[conversion_id]['chapters_info'] = cleaned
    return jsonify({'success': True, 'chapters_info': cleaned})

@app.route('/api/conversions/<conversion_id>/page-text/<int:page_number>')
def get_conversion_page_text(conversion_id, page_number):
    auth_err = _require_login()
    if auth_err:
        return auth_err

    saved = _db_get_conversion(conversion_id)
    if not saved:
        return jsonify({'error': 'Conversão não encontrada'}), 404
    uid = saved.get('user_uid')
    if uid and g.firebase_user and uid != g.firebase_user.get('uid'):
        return jsonify({'error': 'Conversão não encontrada'}), 404

    if FIRESTORE_CLIENT is not None:
        try:
            doc_id = str(int(page_number))
            pdoc = (
                FIRESTORE_CLIENT.collection('conversions')
                .document(conversion_id)
                .collection('pages')
                .document(doc_id)
                .get()
            )
            if not pdoc.exists:
                return jsonify({'error': 'Página não encontrada'}), 404
            pd = pdoc.to_dict() or {}
            return jsonify({
                'page_number': int(page_number),
                'display_label': pd.get('display_label'),
                'text': pd.get('text') or '',
                'alignment': pd.get('alignment') or None
            })
        except Exception as e:
            return jsonify({'error': f'Erro ao carregar texto: {str(e)}'}), 500

    with DB_LOCK:
        conn = _db_connect()
        try:
            row = conn.execute(
                f'SELECT display_label, text, alignment_json FROM pages WHERE conversion_id={_ph()} AND page_number={_ph()}',
                (conversion_id, int(page_number))
            ).fetchone()
            if not row:
                return jsonify({'error': 'Página não encontrada'}), 404
            d = dict(row)
            alignment = None
            if d.get('alignment_json'):
                try:
                    alignment = json.loads(d.get('alignment_json'))
                except Exception:
                    alignment = None
            return jsonify({
                'page_number': int(page_number),
                'display_label': d.get('display_label'),
                'text': d.get('text') or '',
                'alignment': alignment
            })
        finally:
            conn.close()

@app.route('/api/conversions/<conversion_id>/delete', methods=['POST'])
def delete_conversion(conversion_id):
    auth_err = _require_login()
    if auth_err:
        return auth_err

    saved = _db_get_conversion(conversion_id)
    if not saved:
        return jsonify({'error': 'Conversão não encontrada'}), 404

    uid = saved.get('user_uid')
    if uid and g.firebase_user and uid != g.firebase_user.get('uid'):
        return jsonify({'error': 'Conversão não encontrada'}), 404

    processing_status.pop(conversion_id, None)

    try:
        sess = _db_get_upload_session(conversion_id)
        if sess:
            tmp = sess.get('temp_path')
            if tmp and os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except Exception:
                    pass
            _db_delete_upload_session(conversion_id)
    except Exception:
        pass

    safe_conversion = secure_filename(conversion_id)
    try:
        shutil.rmtree(os.path.join(app.config['AUDIO_FOLDER'], safe_conversion), ignore_errors=True)
    except Exception:
        pass

    try:
        if os.path.isdir(app.config['UPLOAD_FOLDER']):
            for name in os.listdir(app.config['UPLOAD_FOLDER']):
                if name.startswith(conversion_id + '_'):
                    try:
                        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], name))
                    except Exception:
                        pass
    except Exception:
        pass

    if FIRESTORE_CLIENT is not None:
        try:
            conv_ref = FIRESTORE_CLIENT.collection('conversions').document(conversion_id)
            for doc in conv_ref.collection('pages').stream():
                try:
                    doc.reference.delete()
                except Exception:
                    pass
            conv_ref.delete()
        except Exception:
            pass

    bucket = _firebase_bucket()
    if bucket is not None:
        for prefix in (f"audio/{conversion_id}/", f"uploads/{conversion_id}/"):
            try:
                for blob in bucket.list_blobs(prefix=prefix):
                    try:
                        blob.delete()
                    except Exception:
                        pass
            except Exception:
                pass

    with DB_LOCK:
        conn = _db_connect()
        try:
            conn.execute(f'DELETE FROM conversions WHERE conversion_id={_ph()}', (conversion_id,))
            conn.commit()
        finally:
            conn.close()

    return jsonify({'ok': True})

@app.route('/download/<conversion_id>/<filename>')
def download_audio(conversion_id, filename):
    try:
        safe_conversion = secure_filename(conversion_id)
        safe_name = secure_filename(filename)
        audio_path = os.path.join(app.config['AUDIO_FOLDER'], safe_conversion, safe_name)
        if not os.path.exists(audio_path):
            audio_path = os.path.join(app.config['AUDIO_FOLDER'], safe_name)
        if not os.path.exists(audio_path):
            saved = _db_get_conversion(conversion_id) or {}
            page = _db_get_page_by_filename(conversion_id, safe_name) or {}
            text = (page.get('text') or '').strip()
            options = saved.get('options') if isinstance(saved.get('options'), dict) else {}
            if text:
                out_dir = os.path.join(app.config['AUDIO_FOLDER'], safe_conversion)
                out_path = os.path.join(out_dir, safe_name)
                res = tts_to_file_with_alignment(
                    text,
                    out_path,
                    lang=str(options.get('lang') or 'pt'),
                    speed=float(options.get('speed') or 1.0),
                    voice_type=str(options.get('voice_type') or 'default'),
                    enhanced_voice=str(options.get('enhanced_voice') or 'default'),
                    tts_engine=str(options.get('tts_engine') or 'gtts'),
                    tts_voice=(options.get('tts_voice') or None),
                    sapi_voice=str(options.get('sapi_voice') or ''),
                    use_offline=bool(options.get('use_offline', False)),
                    normalize_audio=bool(options.get('normalize_audio', False)),
                    trim_silence=bool(options.get('trim_silence', False))
                )
                audio_path = res.get('path') or audio_path
                if audio_path and os.path.exists(audio_path):
                    try:
                        _db_update_page_full_path(conversion_id, safe_name, audio_path)
                    except Exception:
                        pass

        if os.path.exists(audio_path):
            resp = send_file(audio_path, as_attachment=True, download_name=safe_name, conditional=False)
            resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            resp.headers['Pragma'] = 'no-cache'
            resp.headers['Expires'] = '0'
            return resp
        else:
            return jsonify({'error': 'Arquivo de áudio não encontrado'}), 404
    except Exception as e:
        return jsonify({'error': f'Erro no download: {str(e)}'}), 500

@app.route('/play/<conversion_id>/<filename>')
def play_audio(conversion_id, filename):
    try:
        safe_conversion = secure_filename(conversion_id)
        safe_name = secure_filename(filename)
        audio_path = os.path.join(app.config['AUDIO_FOLDER'], safe_conversion, safe_name)
        if not os.path.exists(audio_path):
            audio_path = os.path.join(app.config['AUDIO_FOLDER'], safe_name)
        if not os.path.exists(audio_path):
            saved = _db_get_conversion(conversion_id) or {}
            page = _db_get_page_by_filename(conversion_id, safe_name) or {}
            text = (page.get('text') or '').strip()
            options = saved.get('options') if isinstance(saved.get('options'), dict) else {}
            if text:
                out_dir = os.path.join(app.config['AUDIO_FOLDER'], safe_conversion)
                out_path = os.path.join(out_dir, safe_name)
                res = tts_to_file_with_alignment(
                    text,
                    out_path,
                    lang=str(options.get('lang') or 'pt'),
                    speed=float(options.get('speed') or 1.0),
                    voice_type=str(options.get('voice_type') or 'default'),
                    enhanced_voice=str(options.get('enhanced_voice') or 'default'),
                    tts_engine=str(options.get('tts_engine') or 'gtts'),
                    tts_voice=(options.get('tts_voice') or None),
                    sapi_voice=str(options.get('sapi_voice') or ''),
                    use_offline=bool(options.get('use_offline', False)),
                    normalize_audio=bool(options.get('normalize_audio', False)),
                    trim_silence=bool(options.get('trim_silence', False))
                )
                audio_path = res.get('path') or audio_path
                if audio_path and os.path.exists(audio_path):
                    try:
                        _db_update_page_full_path(conversion_id, safe_name, audio_path)
                    except Exception:
                        pass

        if os.path.exists(audio_path):
            resp = send_file(audio_path, conditional=False)
            resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            resp.headers['Pragma'] = 'no-cache'
            resp.headers['Expires'] = '0'
            return resp
        else:
            return jsonify({'error': 'Arquivo de áudio não encontrado'}), 404
    except Exception as e:
        return jsonify({'error': f'Erro ao reproduzir: {str(e)}'}), 500

@app.after_request
def add_dynamic_no_cache_headers(resp):
    try:
        p = request.path or ''
        if resp.mimetype == 'text/html' or p == '/' or p.startswith('/status/') or p.startswith('/upload') or p.startswith('/merge-audio/') or p.startswith('/download-merged/') or p.startswith('/s/'):
            resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            resp.headers['Pragma'] = 'no-cache'
            resp.headers['Expires'] = '0'
        resp.headers['Cross-Origin-Opener-Policy'] = 'same-origin-allow-popups'
        resp.headers['Cross-Origin-Embedder-Policy'] = 'unsafe-none'
    except Exception:
        pass
    return resp

@app.route('/favicon.ico')
def favicon():
    try:
        candidates = [
            os.path.join('static', 'favicon.ico'),
            os.path.join('static', 'icons', 'icon-192x192.png')
        ]
        for p in candidates:
            if os.path.exists(p):
                return send_file(p)
    except Exception:
        pass
    return ('', 204)

@app.route('/auth/me')
def auth_me():
    auth_err = _require_login()
    if auth_err:
        return auth_err
    return jsonify({'user': g.firebase_user})

@app.route('/config')
def public_config():
    return jsonify({
        'require_auth': bool(REQUIRE_AUTH),
        'firebase_project_id': app.config.get('FIREBASE_PROJECT_ID', ''),
        'firebase_auth_domain': 'conversao-de-livro-para-audio.firebaseapp.com'
    })

@app.route('/ffmpeg-status')
def ffmpeg_status():
    _configure_ffmpeg()
    return jsonify({'available': bool(FFMPEG_AVAILABLE), 'path': FFMPEG_PATH, 'ffprobe_path': FFPROBE_PATH})

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
    if VOICE_ENHANCER_AVAILABLE:
        return jsonify({
            'available': True,
            'profiles': ENHANCED_VOICE_PROFILES,
            'description': 'Vozes ultra-naturais com IA (perfis GTTS)'
        })
    return jsonify({
        'available': False,
        'message': 'Vozes melhoradas não disponíveis.'
    })

@app.route('/tts-voices')
def get_tts_voices():
    global EDGE_TTS_AVAILABLE, edge_tts, EDGE_TTS_ERROR
    if not EDGE_TTS_AVAILABLE:
        try:
            import edge_tts as _edge_tts
            edge_tts = _edge_tts
            EDGE_TTS_AVAILABLE = True
            EDGE_TTS_ERROR = ''
        except Exception as e:
            EDGE_TTS_AVAILABLE = False
            EDGE_TTS_ERROR = str(e)
            return jsonify({'available': False, 'engine': 'edge', 'message': EDGE_TTS_ERROR or 'Edge TTS não disponível'}), 200

    now = time.time()
    if (now - EDGE_VOICES_CACHE['loaded_at']) > 3600 or not EDGE_VOICES_CACHE['voices']:
        async def _list():
            return await edge_tts.list_voices()
        try:
            voices = asyncio.run(_list())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                voices = loop.run_until_complete(_list())
            finally:
                loop.close()
        EDGE_VOICES_CACHE['voices'] = voices or []
        EDGE_VOICES_CACHE['loaded_at'] = now

    lang = request.args.get('lang', 'pt').strip().lower()
    voices = EDGE_VOICES_CACHE['voices']
    filtered = []
    for v in voices:
        locale = str(v.get('Locale', '')).lower()
        if not locale:
            continue
        if lang == 'pt' and not locale.startswith('pt'):
            continue
        if lang != 'pt' and not locale.startswith(lang):
            continue
        filtered.append({
            'shortName': v.get('ShortName'),
            'friendlyName': v.get('FriendlyName') or v.get('ShortName'),
            'locale': v.get('Locale'),
            'gender': v.get('Gender')
        })
        if len(filtered) >= 40:
            break

    return jsonify({'available': True, 'engine': 'edge', 'voices': filtered})

@app.route('/extract-text', methods=['POST'])
def extract_text_for_editing():
    """Extract text from file for editing before conversion"""
    if 'file' not in request.files:
        return jsonify({'error': 'Nenhum arquivo enviado'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Nenhum arquivo selecionado'}), 400
    
    if file and allowed_file(file.filename):
        # Save uploaded file temporarily
        filename = secure_filename(file.filename)
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], f"temp_{filename}")
        file.save(temp_path)
        
        try:
            # Extract text
            file_type = filename.rsplit('.', 1)[1].lower()
            pages_data = extract_text_from_file(temp_path, file_type, options={'lang': 'pt', 'use_ocr': True})
            
            # Combine all text for editing
            full_text = '\n\n'.join([f"--- Página {page['page_number']} ---\n{page['text']}" for page in pages_data])
            
            # Clean up temp file
            os.remove(temp_path)
            
            return jsonify({
                'success': True,
                'pages': pages_data,
                'full_text': full_text,
                'total_pages': len(pages_data)
            })
            
        except Exception as e:
            # Clean up temp file on error
            try:
                os.remove(temp_path)
            except:
                pass
            return jsonify({'error': f'Erro ao extrair texto: {str(e)}'}), 500
    
    return jsonify({'error': 'Tipo de arquivo não permitido.'}), 400

@app.route('/convert-edited-text', methods=['POST'])
def convert_edited_text():
    """Convert edited text to audio"""
    try:
        data = request.get_json()
        
        if not data or 'pages' not in data:
            return jsonify({'error': 'Dados inválidos'}), 400
        
        pages = data['pages']
        options = data.get('options', {
            'lang': 'pt',
            'speed': 1.0,
            'voice_type': 'default'
        })
        if 'split_mode' not in options:
            options['split_mode'] = 'chapter'
        
        # Generate unique ID for this conversion
        conversion_id = str(uuid.uuid4())
        
        # Start processing in background
        processing_status[conversion_id] = {
            'status': 'processing',
            'progress': 0,
            'message': 'Iniciando processamento de texto editado...',
            'filename': 'texto_editado',
            'created_at': datetime.now().isoformat(),
            'options': options
        }

        _db_upsert_conversion(
            conversion_id,
            source_filename='texto_editado',
            source_type='edited_text',
            created_at=processing_status[conversion_id]['created_at'],
            status='processing',
            progress=0,
            message=processing_status[conversion_id]['message'],
            options_json=json.dumps(options, ensure_ascii=False),
            from_edited_text=1,
            client_ip=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        # Start background processing
        thread = threading.Thread(target=process_edited_text, args=(conversion_id, pages, options))
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'conversion_id': conversion_id,
            'message': 'Texto editado enviado com sucesso. Processando...',
            'options': options
        })
        
    except Exception as e:
        return jsonify({'error': f'Erro ao processar texto editado: {str(e)}'}), 500

def process_edited_text(conversion_id, pages, options):
    """Process edited text pages to audio"""
    try:
        # Update status
        processing_status[conversion_id]['status'] = 'processing'
        processing_status[conversion_id]['progress'] = 10
        processing_status[conversion_id]['message'] = 'Processando texto editado...'
        _db_upsert_conversion(
            conversion_id,
            status='processing',
            progress=int(processing_status[conversion_id]['progress']),
            message=processing_status[conversion_id]['message'],
            options_json=json.dumps(options, ensure_ascii=False),
            from_edited_text=1
        )
        
        split_mode = options.get('split_mode', 'chapter')
        if split_mode not in ('page', 'chapter'):
            split_mode = 'chapter'

        total_pages = len(pages)
        processing_status[conversion_id]['total_pages'] = total_pages
        processing_status[conversion_id]['message'] = f'Convertendo texto editado...'
        _db_upsert_conversion(
            conversion_id,
            status='processing',
            progress=int(processing_status[conversion_id]['progress']),
            message=processing_status[conversion_id]['message']
        )
        
        # Convert to audio
        audio_output_dir = os.path.join(app.config['AUDIO_FOLDER'], conversion_id)
        audio_files = []
        chapters_info = []

        if split_mode == 'chapter':
            pages_data = []
            for i, p in enumerate(pages or []):
                pages_data.append({'page_number': p.get('page_number', i + 1), 'text': p.get('text', '')})
            chapters = detect_chapters_from_pages(pages_data)
            if not chapters:
                chapters = [{'chapter_index': 1, 'title': 'Conteúdo', 'text': '\n\n'.join([p.get('text', '') for p in pages_data if p.get('text')])}]

            unit_items = []
            seq = 0
            total_units = 0
            chapters_info = []
            for ch in chapters:
                ch_text = clean_text_for_tts(ch.get('text', ''))
                parts = split_text_chunks(ch_text, max_chars=1800)
                if not parts:
                    continue
                chapters_info.append({'chapter_index': ch.get('chapter_index'), 'title': ch.get('title'), 'parts': len(parts)})
                total_units += len(parts)

            total_units = max(1, int(total_units))

            for ch in chapters:
                ch_text = clean_text_for_tts(ch.get('text', ''))
                parts = split_text_chunks(ch_text, max_chars=1800)
                if not parts:
                    continue
                for part_i, part_text in enumerate(parts, start=1):
                    ctrl = _get_control_status(conversion_id)
                    if ctrl == 'cancel':
                        processing_status[conversion_id]['status'] = 'cancelled'
                        processing_status[conversion_id]['message'] = 'Conversão cancelada.'
                        _db_upsert_conversion(
                            conversion_id,
                            status='cancelled',
                            message=processing_status[conversion_id]['message'],
                            control_status='cancel',
                            progress=int(processing_status[conversion_id].get('progress') or 0),
                            from_edited_text=1
                        )
                        return
                    if ctrl == 'pause':
                        processing_status[conversion_id]['status'] = 'paused'
                        processing_status[conversion_id]['message'] = 'Conversão pausada.'
                        _db_upsert_conversion(
                            conversion_id,
                            status='paused',
                            message=processing_status[conversion_id]['message'],
                            control_status='pause',
                            progress=int(processing_status[conversion_id].get('progress') or 0),
                            from_edited_text=1
                        )
                        return
                    seq += 1
                    filename = f"capitulo_{int(ch.get('chapter_index') or 1):02d}_parte_{part_i:02d}.mp3"
                    out_path = os.path.join(audio_output_dir, filename)
                    progress = int(20 + (75 * (seq / total_units)))
                    processing_status[conversion_id]['progress'] = min(99, max(0, progress))
                    processing_status[conversion_id]['message'] = f'Convertendo {ch.get("title")} (parte {part_i}/{len(parts)})...'
                    _db_upsert_conversion(
                        conversion_id,
                        status='processing',
                        progress=int(processing_status[conversion_id]['progress']),
                        message=processing_status[conversion_id]['message']
                    )
                    tts_res = tts_to_file_with_alignment(
                        part_text,
                        out_path,
                        lang=options['lang'],
                        speed=options['speed'],
                        voice_type=options['voice_type'],
                        enhanced_voice=options.get('enhanced_voice', 'default'),
                        tts_engine=options.get('tts_engine', 'gtts'),
                        tts_voice=options.get('tts_voice') or None,
                        sapi_voice=options.get('sapi_voice', ''),
                        use_offline=bool(options.get('use_offline', False)),
                        normalize_audio=bool(options.get('normalize_audio', False)),
                        trim_silence=bool(options.get('trim_silence', False))
                    )
                    audio_file = tts_res.get('path')
                    alignment = tts_res.get('alignment')
                    if audio_file:
                        display = f"{ch.get('title')} — Parte {part_i}"
                        unit_items.append({
                            'page_number': seq,
                            'filename': os.path.basename(audio_file),
                            'full_path': audio_file,
                            'display_label': display,
                            'chapter_index': ch.get('chapter_index'),
                            'chapter_title': ch.get('title'),
                            'part_index': part_i,
                            'part_count': len(parts)
                        })
                        _db_upsert_page(
                            conversion_id,
                            seq,
                            os.path.basename(audio_file),
                            audio_file,
                            len(part_text or ''),
                            text=part_text,
                            display_label=display,
                            alignment=alignment
                        )

            audio_files = unit_items
        else:
        
            for i, page_data in enumerate(pages):
                ctrl = _get_control_status(conversion_id)
                if ctrl == 'cancel':
                    processing_status[conversion_id]['status'] = 'cancelled'
                    processing_status[conversion_id]['message'] = 'Conversão cancelada.'
                    _db_upsert_conversion(
                        conversion_id,
                        status='cancelled',
                        message=processing_status[conversion_id]['message'],
                        control_status='cancel',
                        progress=int(processing_status[conversion_id].get('progress') or 0),
                        from_edited_text=1
                    )
                    return
                if ctrl == 'pause':
                    processing_status[conversion_id]['status'] = 'paused'
                    processing_status[conversion_id]['message'] = 'Conversão pausada.'
                    _db_upsert_conversion(
                        conversion_id,
                        status='paused',
                        message=processing_status[conversion_id]['message'],
                        control_status='pause',
                        progress=int(processing_status[conversion_id].get('progress') or 0),
                        from_edited_text=1
                    )
                    return
                page_number = page_data.get('page_number', i + 1)
                page_text = page_data.get('text', '')
            
                # Update progress for each page
                page_progress = int(20 + (75 * (i + 1) / max(1, total_pages)))
                processing_status[conversion_id]['progress'] = min(99, max(0, page_progress))
                processing_status[conversion_id]['message'] = f'Convertendo página editada {page_number}/{total_pages} ({options["lang"]})...'
                _db_upsert_conversion(
                    conversion_id,
                    status='processing',
                    progress=int(processing_status[conversion_id]['progress']),
                    message=processing_status[conversion_id]['message']
                )
            
                # Convert this page to audio with options
                audio_file = text_to_speech_page(
                    page_text, 
                    audio_output_dir, 
                    page_number, 
                    lang=options['lang'],
                    speed=options['speed'],
                    voice_type=options['voice_type'],
                    enhanced_voice=options.get('enhanced_voice', 'default'),
                    tts_engine=options.get('tts_engine', 'gtts'),
                    tts_voice=options.get('tts_voice') or None,
                    sapi_voice=options.get('sapi_voice', ''),
                    use_offline=bool(options.get('use_offline', False))
                )
            
                if audio_file:
                    audio_files.append({
                        'page_number': page_number,
                        'filename': os.path.basename(audio_file),
                        'full_path': audio_file
                    })
                    print(f"Página editada {page_number} convertida com sucesso: {audio_file}")
                    _db_upsert_page(
                        conversion_id,
                        page_number,
                        os.path.basename(audio_file),
                        audio_file,
                        len(page_text or ''),
                        text=page_text,
                        display_label=None
                    )
        
        if not audio_files:
            processing_status[conversion_id]['status'] = 'error'
            processing_status[conversion_id]['message'] = 'Não foi possível converter nenhuma página editada'
            _db_upsert_conversion(
                conversion_id,
                status='error',
                progress=int(processing_status[conversion_id].get('progress') or 0),
                message=processing_status[conversion_id]['message'],
                from_edited_text=1
            )
            return
        
        # Sort files by page number
        audio_files.sort(key=lambda x: x['page_number'])

        processing_status[conversion_id]['progress'] = 99
        processing_status[conversion_id]['message'] = 'Finalizando...'
        _db_upsert_conversion(
            conversion_id,
            status='processing',
            progress=int(processing_status[conversion_id]['progress']),
            message=processing_status[conversion_id]['message'],
            from_edited_text=1
        )
        
        # Update status with completion
        processing_status[conversion_id]['status'] = 'completed'
        processing_status[conversion_id]['progress'] = 100
        if split_mode == 'chapter':
            processing_status[conversion_id]['message'] = f'Conversão concluída! {len(audio_files)} partes por capítulo geradas.'
        else:
            processing_status[conversion_id]['message'] = f'Conversão concluída! {len(audio_files)} páginas editadas convertidas.'
        processing_status[conversion_id]['audio_files'] = [item['full_path'] for item in audio_files]
        processing_status[conversion_id]['pages_info'] = audio_files
        processing_status[conversion_id]['chapters_info'] = chapters_info
        processing_status[conversion_id]['total_chunks'] = len(audio_files)
        processing_status[conversion_id]['options'] = options
        processing_status[conversion_id]['from_edited_text'] = True

        _db_upsert_conversion(
            conversion_id,
            status='completed',
            progress=100,
            message=processing_status[conversion_id]['message'],
            options_json=json.dumps(options, ensure_ascii=False),
            chapters_json=json.dumps(chapters_info, ensure_ascii=False),
            from_edited_text=1
        )
            
    except Exception as e:
        processing_status[conversion_id]['status'] = 'error'
        processing_status[conversion_id]['message'] = f'Erro no processamento: {str(e)}'
        processing_status[conversion_id]['progress'] = 0
        _db_upsert_conversion(
            conversion_id,
            status='error',
            progress=0,
            message=processing_status[conversion_id]['message'],
            from_edited_text=1
        )

@app.route('/offline-status')
def get_offline_status():
    """Check offline TTS availability"""
    voices = []
    if SAPI_AVAILABLE:
        try:
            sapi = win32com.client.Dispatch("SAPI.SpVoice")
            for v in sapi.GetVoices():
                voices.append(v.GetDescription())
        except Exception:
            voices = []
    return jsonify({
        'sapi_available': SAPI_AVAILABLE,
        'offline_tts_available': OFFLINE_TTS_AVAILABLE,
        'voices': voices
    })

def merge_audio_files(audio_files, output_path, add_pause=True):
    _configure_ffmpeg()
    if not PYDUB_AVAILABLE or not FFMPEG_AVAILABLE:
        return None
    if not audio_files:
        return None
    combined = AudioSegment.from_mp3(audio_files[0])
    for audio_file in audio_files[1:]:
        try:
            audio = AudioSegment.from_mp3(audio_file)
            if add_pause:
                combined += AudioSegment.silent(duration=1000)
            combined += audio
        except Exception:
            continue
    combined.export(output_path, format="mp3", bitrate="192k")
    return output_path

def merge_wav_files(audio_files, output_path, add_pause=True, pause_ms=1000):
    if not audio_files:
        return None
    try:
        with wave.open(audio_files[0], 'rb') as w0:
            params = w0.getparams()
    except Exception:
        return None

    silence_frames = b''
    if add_pause and pause_ms > 0:
        frames = int(params.framerate * (pause_ms / 1000.0))
        silence_frames = (b'\x00' * (frames * params.nchannels * params.sampwidth))

    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with wave.open(output_path, 'wb') as out:
            out.setnchannels(params.nchannels)
            out.setsampwidth(params.sampwidth)
            out.setframerate(params.framerate)
            for idx, fp in enumerate(audio_files):
                try:
                    with wave.open(fp, 'rb') as w:
                        if w.getnchannels() != params.nchannels or w.getsampwidth() != params.sampwidth or w.getframerate() != params.framerate:
                            return None
                        data = w.readframes(w.getnframes())
                        if idx > 0 and silence_frames:
                            out.writeframes(silence_frames)
                        out.writeframes(data)
                except Exception:
                    continue
        return output_path if os.path.exists(output_path) else None
    except Exception:
        return None

@app.route('/merge-audio/<conversion_id>')
def merge_audio(conversion_id):
    try:
        auth_err = _require_login()
        if auth_err:
            return auth_err
        _configure_ffmpeg()
        status = processing_status.get(conversion_id)
        if not status:
            status = _db_get_conversion(conversion_id)
        if not status:
            return jsonify({'error': 'Conversão não encontrada'}), 404
        uid = status.get('user_uid')
        if uid and g.firebase_user and uid != g.firebase_user.get('uid'):
            return jsonify({'error': 'Conversão não encontrada'}), 404
        if status.get('status') != 'completed':
            return jsonify({'error': 'Conversão ainda não foi concluída'}), 400
        audio_files = []
        pages_info = status.get('pages_info', []) or []
        for page_info in pages_info:
            p = page_info.get('full_path')
            filename = page_info.get('filename')
            resolved = _resolve_audio_path(conversion_id, p, filename=filename)
            if resolved:
                audio_files.append(resolved)
        if not audio_files:
            return jsonify({
                'error': 'Nenhum arquivo de áudio local encontrado para mesclar. Refaça a conversão ou verifique se a pasta audio/ existe no servidor.',
                'pages_count': len(pages_info),
                'audio_folder': app.config['AUDIO_FOLDER'],
                'ffmpeg_available': bool(FFMPEG_AVAILABLE),
                'ffmpeg_path': FFMPEG_PATH
            }), 404

        all_wav = all(str(p).lower().endswith('.wav') for p in audio_files)
        if not FFMPEG_AVAILABLE and not all_wav:
            return jsonify({'error': 'FFmpeg não encontrado. Instale o FFmpeg para mesclar MP3. Para WAV, a mesclagem funciona sem FFmpeg.'}), 500
        if not all_wav and not PYDUB_AVAILABLE:
            return jsonify({'error': 'Funcionalidade de mesclagem MP3 não disponível. Instale pydub.'}), 500

        merge_id = str(uuid.uuid4())
        if conversion_id not in processing_status:
            processing_status[conversion_id] = status
        processing_status[conversion_id]['merge_status'] = 'processing'
        processing_status[conversion_id]['merge_progress'] = 0
        processing_status[conversion_id]['merge_message'] = 'Iniciando mesclagem dos áudios...'
        _db_upsert_conversion(
            conversion_id,
            merge_status='processing',
            merge_progress=0,
            merge_message=processing_status[conversion_id]['merge_message']
        )
        target = process_merge_wav if all_wav else process_merge
        thread = threading.Thread(target=target, args=(conversion_id, merge_id, audio_files))
        thread.daemon = True
        thread.start()
        return jsonify({'merge_id': merge_id, 'message': 'Mesclagem iniciada em segundo plano...'})
    except Exception as e:
        return jsonify({'error': f'Erro ao iniciar mesclagem: {str(e)}'}), 500

@app.route('/download-merged/<conversion_id>')
def download_merged_audio(conversion_id):
    try:
        auth_err = _require_login()
        if auth_err:
            return auth_err
        status = processing_status.get(conversion_id)
        if not status:
            status = _db_get_conversion(conversion_id)
        if not status:
            return jsonify({'error': 'Conversão não encontrada'}), 404
        uid = status.get('user_uid')
        if uid and g.firebase_user and uid != g.firebase_user.get('uid'):
            return jsonify({'error': 'Conversão não encontrada'}), 404
        merged_file = status.get('merged_file')
        if not merged_file or not os.path.exists(merged_file):
            return jsonify({'error': 'Arquivo mesclado não encontrado'}), 404
        book_title = status.get('book_title') or status.get('source_filename') or f"audiobook_{conversion_id}"
        book_title = build_book_title(book_title)
        ext = os.path.splitext(merged_file)[1].lower() or '.mp3'
        filename = f"{book_title}_mesclado{ext}"
        return send_file(merged_file, as_attachment=True, download_name=filename, conditional=False)
    except Exception as e:
        return jsonify({'error': f'Erro no download: {str(e)}'}), 500

@app.route('/download-m4b/<conversion_id>')
def download_m4b(conversion_id):
    try:
        auth_err = _require_login()
        if auth_err:
            return auth_err
        _configure_ffmpeg()
        if not FFMPEG_AVAILABLE:
            return jsonify({'error': 'FFmpeg não encontrado'}), 500
        status = processing_status.get(conversion_id)
        if not status:
            status = _db_get_conversion(conversion_id)
        if not status:
            return jsonify({'error': 'Conversão não encontrada'}), 404
        uid = status.get('user_uid')
        if uid and g.firebase_user and uid != g.firebase_user.get('uid'):
            return jsonify({'error': 'Conversão não encontrada'}), 404
        merged_file = status.get('merged_file')
        if not merged_file or not os.path.exists(merged_file):
            return jsonify({'error': 'Arquivo mesclado não encontrado. Use “Juntar Áudios” primeiro.'}), 404

        book_title = status.get('book_title') or status.get('source_filename') or f"audiobook_{conversion_id}"
        book_title = build_book_title(book_title)
        filename = f"{book_title}.m4b"

        tmp = tempfile.NamedTemporaryFile(prefix=f"{secure_filename(conversion_id)}_", suffix=".m4b", delete=False)
        out_path = tmp.name
        tmp.close()

        ff = FFMPEG_PATH or 'ffmpeg'
        cmd = [
            ff, '-y',
            '-i', merged_file,
            '-vn',
            '-c:a', 'aac',
            '-b:a', '128k',
            '-movflags', '+faststart',
            out_path
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        except Exception:
            try:
                os.remove(out_path)
            except Exception:
                pass
            return jsonify({'error': 'Erro ao gerar M4B via FFmpeg'}), 500

        @after_this_request
        def _cleanup(resp):
            try:
                os.remove(out_path)
            except Exception:
                pass
            return resp

        return send_file(out_path, as_attachment=True, download_name=filename, conditional=False)
    except Exception as e:
        return jsonify({'error': f'Erro no download: {str(e)}'}), 500

def _zip_cleanup(now=None):
    now = now if isinstance(now, (int, float)) else time.time()
    with ZIP_LOCK:
        for cid, st in list((ZIP_STATUS or {}).items()):
            created = st.get('created_at') or 0
            if created and (now - float(created)) > ZIP_TTL_S:
                ZIP_STATUS.pop(cid, None)

def _zip_get(conversion_id):
    with ZIP_LOCK:
        st = ZIP_STATUS.get(conversion_id) or {}
        return dict(st)

def _zip_set(conversion_id, **fields):
    with ZIP_LOCK:
        cur = ZIP_STATUS.get(conversion_id) or {}
        cur.update(fields)
        ZIP_STATUS[conversion_id] = cur
        return dict(cur)

def _build_zip_entries(conversion_id, status):
    pages_info = status.get('pages_info', []) or []
    entries = []
    for p in pages_info:
        filename = secure_filename(p.get('filename') or '')
        if not filename:
            continue
        arc = os.path.basename(filename)
        label = (p.get('display_label') or '').strip()
        folder = ''
        if label:
            if '—' in label:
                folder = label.split('—', 1)[0].strip()
            else:
                folder = label.strip()
        folder = secure_filename(folder) if folder else ''
        if folder:
            arc = f"{folder}/{arc}"
        entries.append({'filename': filename, 'arcname': arc})
    merged_file = status.get('merged_file')
    if merged_file and os.path.exists(merged_file):
        entries.append({'full_path': merged_file, 'arcname': os.path.basename(merged_file)})
    return entries

def _collect_zip_files(conversion_id, status_snapshot):
    entries = _build_zip_entries(conversion_id, status_snapshot or {})
    files = []
    added = set()
    for ent in entries:
        full_path = ent.get('full_path')
        arcname = ent.get('arcname') or ''
        if not full_path:
            fn = ent.get('filename') or ''
            if fn:
                full_path = _resolve_audio_path(conversion_id, None, filename=fn)
        if not full_path or not os.path.exists(full_path):
            continue
        if not arcname:
            arcname = os.path.basename(full_path)
        if arcname in added:
            base, ext = os.path.splitext(arcname)
            k = 2
            while f"{base}_{k}{ext}" in added:
                k += 1
            arcname = f"{base}_{k}{ext}"
        added.add(arcname)
        files.append((full_path, arcname))
    return files

def _stream_zip_response(conversion_id, status_snapshot, zip_name):
    files = _collect_zip_files(conversion_id, status_snapshot)
    if not files:
        return jsonify({'error': 'Nenhum arquivo encontrado para compactar'}), 404
    if zipstream is None:
        return jsonify({'error': 'ZIP streaming não disponível no servidor. Instale zipstream-ng.'}), 500
    z = zipstream.ZipFile(mode='w', compression=zipfile.ZIP_STORED)
    for full_path, arcname in files:
        try:
            z.write(full_path, arcname)
        except Exception:
            continue
    resp = Response(z, mimetype='application/zip')
    resp.headers['Content-Disposition'] = f'attachment; filename=\"{zip_name}\"'
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

def _zip_worker(conversion_id, zip_name, status_snapshot):
    try:
        _zip_set(conversion_id, status='preparing', progress=0, message='Preparando ZIP...', zip_name=zip_name)
        files = _collect_zip_files(conversion_id, status_snapshot or {})
        if not files:
            _zip_set(conversion_id, status='error', progress=0, message='Nenhum arquivo encontrado para compactar.')
            return
        _zip_set(conversion_id, status='completed', progress=100, message=f'ZIP pronto ({len(files)} arquivos).', created_at=time.time())
    except Exception as e:
        _zip_set(conversion_id, status='error', progress=0, message=f'Erro ao gerar ZIP: {str(e)}')

@app.route('/api/conversions/<conversion_id>/zip/start', methods=['POST'])
def start_zip_job(conversion_id):
    auth_err = _require_login()
    if auth_err:
        return auth_err

    _zip_cleanup()

    status = processing_status.get(conversion_id) or _db_get_conversion(conversion_id)
    if not status:
        return jsonify({'error': 'Conversão não encontrada'}), 404
    uid = status.get('user_uid')
    if uid and g.firebase_user and uid != g.firebase_user.get('uid'):
        return jsonify({'error': 'Conversão não encontrada'}), 404

    cur = _zip_get(conversion_id)
    if cur and cur.get('status') in ('preparing', 'zipping'):
        return jsonify({'success': True, 'status': cur}), 200

    book_title = status.get('book_title') or status.get('source_filename') or f"audiobook_{conversion_id}"
    book_title = build_book_title(book_title)
    zip_name = f"{book_title}_audios.zip"

    _zip_set(conversion_id, status='queued', progress=0, message='Na fila para gerar ZIP...', zip_name=zip_name, zip_path='', created_at=time.time())
    th = threading.Thread(target=_zip_worker, args=(conversion_id, zip_name, status), daemon=True)
    th.start()
    return jsonify({'success': True, 'status': _zip_get(conversion_id)}), 200

@app.route('/api/conversions/<conversion_id>/zip/status')
def zip_job_status(conversion_id):
    auth_err = _require_login()
    if auth_err:
        return auth_err
    _zip_cleanup()
    status = processing_status.get(conversion_id) or _db_get_conversion(conversion_id)
    if not status:
        return jsonify({'error': 'Conversão não encontrada'}), 404
    uid = status.get('user_uid')
    if uid and g.firebase_user and uid != g.firebase_user.get('uid'):
        return jsonify({'error': 'Conversão não encontrada'}), 404
    st = _zip_get(conversion_id)
    if not st:
        return jsonify({'status': 'idle', 'progress': 0, 'message': ''})
    out = {
        'status': st.get('status') or 'idle',
        'progress': int(st.get('progress') or 0),
        'message': st.get('message') or '',
        'zip_name': st.get('zip_name') or ''
    }
    if (st.get('status') or '') == 'completed':
        out['download_url'] = f"/api/conversions/{conversion_id}/zip/stream"
    return jsonify(out)

@app.route('/api/conversions/<conversion_id>/zip/download')
def zip_job_download(conversion_id):
    auth_err = _require_login()
    if auth_err:
        return auth_err
    _zip_cleanup()
    status = processing_status.get(conversion_id) or _db_get_conversion(conversion_id)
    if not status:
        return jsonify({'error': 'Conversão não encontrada'}), 404
    uid = status.get('user_uid')
    if uid and g.firebase_user and uid != g.firebase_user.get('uid'):
        return jsonify({'error': 'Conversão não encontrada'}), 404
    book_title = status.get('book_title') or status.get('source_filename') or f"audiobook_{conversion_id}"
    book_title = build_book_title(book_title)
    zip_name = f"{book_title}_audios.zip"
    return _stream_zip_response(conversion_id, status, zip_name)

@app.route('/api/conversions/<conversion_id>/zip/stream')
def zip_job_stream(conversion_id):
    auth_err = _require_login()
    if auth_err:
        return auth_err
    status = processing_status.get(conversion_id) or _db_get_conversion(conversion_id)
    if not status:
        return jsonify({'error': 'Conversão não encontrada'}), 404
    uid = status.get('user_uid')
    if uid and g.firebase_user and uid != g.firebase_user.get('uid'):
        return jsonify({'error': 'Conversão não encontrada'}), 404
    book_title = status.get('book_title') or status.get('source_filename') or f"audiobook_{conversion_id}"
    book_title = build_book_title(book_title)
    zip_name = f"{book_title}_audios.zip"
    return _stream_zip_response(conversion_id, status, zip_name)

@app.route('/download-zip/<conversion_id>')
def download_zip(conversion_id):
    auth_err = _require_login()
    if auth_err:
        return auth_err

    status = processing_status.get(conversion_id)
    if not status:
        status = _db_get_conversion(conversion_id)
    if not status:
        return jsonify({'error': 'Conversão não encontrada'}), 404
    uid = status.get('user_uid')
    if uid and g.firebase_user and uid != g.firebase_user.get('uid'):
        return jsonify({'error': 'Conversão não encontrada'}), 404

    book_title = status.get('book_title') or status.get('source_filename') or f"audiobook_{conversion_id}"
    book_title = build_book_title(book_title)
    zip_name = f"{book_title}_audios.zip"
    return _stream_zip_response(conversion_id, status, zip_name)

def process_merge(conversion_id, merge_id, audio_files):
    try:
        processing_status[conversion_id]['merge_status'] = 'processing'
        processing_status[conversion_id]['merge_progress'] = 10
        processing_status[conversion_id]['merge_message'] = 'Mesclando arquivos de áudio...'
        _db_upsert_conversion(
            conversion_id,
            merge_status='processing',
            merge_progress=10,
            merge_message=processing_status[conversion_id]['merge_message']
        )
        output_dir = os.path.join(app.config['AUDIO_FOLDER'], conversion_id)
        os.makedirs(output_dir, exist_ok=True)
        book_title = None
        if conversion_id in processing_status:
            book_title = processing_status[conversion_id].get('book_title')
        if not book_title:
            saved = _db_get_conversion(conversion_id)
            if saved:
                book_title = saved.get('book_title')
        if not book_title:
            book_title = f"audiobook_{conversion_id}"
        book_title = build_book_title(book_title)

        merged_filename = f"{book_title}_mesclado.mp3"
        merged_file_path = os.path.join(output_dir, merged_filename)
        processing_status[conversion_id]['merge_progress'] = 50
        processing_status[conversion_id]['merge_message'] = 'Processando áudio mesclado...'
        _db_upsert_conversion(
            conversion_id,
            merge_status='processing',
            merge_progress=50,
            merge_message=processing_status[conversion_id]['merge_message']
        )
        result = merge_audio_files(audio_files, merged_file_path, add_pause=True)
        if result:
            merged_remote = _storage_upload(result, f"audio/{conversion_id}/{merged_filename}", content_type='audio/mpeg')
            processing_status[conversion_id]['merge_status'] = 'completed'
            processing_status[conversion_id]['merge_progress'] = 100
            processing_status[conversion_id]['merge_message'] = 'Mesclagem concluída com sucesso!'
            processing_status[conversion_id]['merged_file'] = merged_file_path
            processing_status[conversion_id]['merged_filename'] = merged_filename
            _db_upsert_conversion(
                conversion_id,
                merge_status='completed',
                merge_progress=100,
                merge_message=processing_status[conversion_id]['merge_message'],
                merged_file=merged_file_path,
                merged_storage=merged_remote
            )
        else:
            processing_status[conversion_id]['merge_status'] = 'error'
            processing_status[conversion_id]['merge_message'] = 'Erro ao mesclar arquivos de áudio'
            _db_upsert_conversion(
                conversion_id,
                merge_status='error',
                merge_message=processing_status[conversion_id]['merge_message']
            )
    except Exception as e:
        processing_status[conversion_id]['merge_status'] = 'error'
        processing_status[conversion_id]['merge_message'] = f'Erro na mesclagem: {str(e)}'
        _db_upsert_conversion(
            conversion_id,
            merge_status='error',
            merge_message=processing_status[conversion_id]['merge_message']
        )

def process_merge_wav(conversion_id, merge_id, audio_files):
    try:
        processing_status[conversion_id]['merge_status'] = 'processing'
        processing_status[conversion_id]['merge_progress'] = 10
        processing_status[conversion_id]['merge_message'] = 'Mesclando arquivos WAV...'
        _db_upsert_conversion(
            conversion_id,
            merge_status='processing',
            merge_progress=10,
            merge_message=processing_status[conversion_id]['merge_message']
        )

        output_dir = os.path.join(app.config['AUDIO_FOLDER'], conversion_id)
        os.makedirs(output_dir, exist_ok=True)
        book_title = None
        if conversion_id in processing_status:
            book_title = processing_status[conversion_id].get('book_title')
        if not book_title:
            saved = _db_get_conversion(conversion_id)
            if saved:
                book_title = saved.get('book_title')
        if not book_title:
            book_title = f"audiobook_{conversion_id}"
        book_title = build_book_title(book_title)

        merged_filename = f"{book_title}_mesclado.wav"
        merged_file_path = os.path.join(output_dir, merged_filename)
        processing_status[conversion_id]['merge_progress'] = 50
        processing_status[conversion_id]['merge_message'] = 'Processando WAV mesclado...'
        _db_upsert_conversion(
            conversion_id,
            merge_status='processing',
            merge_progress=50,
            merge_message=processing_status[conversion_id]['merge_message']
        )

        result = merge_wav_files(audio_files, merged_file_path, add_pause=True)
        if result:
            merged_remote = _storage_upload(result, f"audio/{conversion_id}/{merged_filename}", content_type='audio/wav')
            processing_status[conversion_id]['merge_status'] = 'completed'
            processing_status[conversion_id]['merge_progress'] = 100
            processing_status[conversion_id]['merge_message'] = 'Mesclagem concluída com sucesso!'
            processing_status[conversion_id]['merged_file'] = merged_file_path
            processing_status[conversion_id]['merged_filename'] = merged_filename
            _db_upsert_conversion(
                conversion_id,
                merge_status='completed',
                merge_progress=100,
                merge_message=processing_status[conversion_id]['merge_message'],
                merged_file=merged_file_path,
                merged_storage=merged_remote
            )
        else:
            processing_status[conversion_id]['merge_status'] = 'error'
            processing_status[conversion_id]['merge_message'] = 'Erro ao mesclar arquivos WAV'
            _db_upsert_conversion(
                conversion_id,
                merge_status='error',
                merge_message=processing_status[conversion_id]['merge_message']
            )
    except Exception as e:
        processing_status[conversion_id]['merge_status'] = 'error'
        processing_status[conversion_id]['merge_message'] = f'Erro na mesclagem: {str(e)}'
        _db_upsert_conversion(
            conversion_id,
            merge_status='error',
            merge_message=processing_status[conversion_id]['merge_message']
        )

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
            'message': 'TTS funcionando corretamente',
            'test_file': test_file
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/cleanup/<conversion_id>')
def cleanup(conversion_id):
    """Clean up files after conversion"""
    try:
        if conversion_id in processing_status:
            status = processing_status[conversion_id]
            if 'audio_files' in status:
                for audio_file in status['audio_files']:
                    try:
                        os.remove(audio_file)
                    except:
                        pass
            del processing_status[conversion_id]
        return jsonify({'message': 'Arquivos removidos com sucesso'})
    except Exception as e:
        return jsonify({'error': f'Erro na limpeza: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=False, use_reloader=False, threaded=True, host='0.0.0.0', port=5000)
