import os
import json
import asyncio
import aiofiles
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import aiohttp
import boto3
from google.cloud import storage as gcs
from azure.storage.blob import BlobServiceClient
import dropbox
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import pickle
import logging

logger = logging.getLogger(__name__)

class CloudStorageConnector:
    """Conector genérico para serviços de armazenamento na nuvem"""
    
    def __init__(self, provider: str, config: Dict[str, Any]):
        self.provider = provider.lower()
        self.config = config
        self.client = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Inicializa cliente específico do provedor"""
        try:
            if self.provider == 'google_drive':
                self._init_google_drive()
            elif self.provider == 'dropbox':
                self._init_dropbox()
            elif self.provider == 'onedrive':
                self._init_onedrive()
            elif self.provider == 'aws_s3':
                self._init_s3()
            elif self.provider == 'google_cloud':
                self._init_google_cloud()
            elif self.provider == 'azure_blob':
                self._init_azure_blob()
            else:
                raise ValueError(f"Provedor não suportado: {self.provider}")
        except Exception as e:
            logger.error(f"Erro ao inicializar cliente {self.provider}: {e}")
            raise
    
    def _init_google_drive(self):
        """Inicializa cliente Google Drive"""
        creds = None
        token_path = self.config.get('token_path', 'token.pickle')
        
        if os.path.exists(token_path):
            with open(token_path, 'rb') as token:
                creds = pickle.load(token)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = self.config.get('auth_flow')
                creds = flow.run_local_server(port=0)
            
            with open(token_path, 'wb') as token:
                pickle.dump(creds, token)
        
        self.client = build('drive', 'v3', credentials=creds)
    
    def _init_dropbox(self):
        """Inicializa cliente Dropbox"""
        self.client = dropbox.Dropbox(
            self.config['access_token'],
            app_key=self.config.get('app_key'),
            app_secret=self.config.get('app_secret')
        )
    
    def _init_onedrive(self):
        """Inicializa cliente OneDrive"""
        self.client = BlobServiceClient(
            account_url=self.config['account_url'],
            credential=self.config['credential']
        )
    
    def _init_s3(self):
        """Inicializa cliente AWS S3"""
        self.client = boto3.client(
            's3',
            aws_access_key_id=self.config['aws_access_key'],
            aws_secret_access_key=self.config['aws_secret_key'],
            region_name=self.config.get('region', 'us-east-1')
        )
    
    def _init_google_cloud(self):
        """Inicializa cliente Google Cloud Storage"""
        self.client = gcs.Client.from_service_account_json(
            self.config['service_account_path']
        )
    
    def _init_azure_blob(self):
        """Inicializa cliente Azure Blob Storage"""
        self.client = BlobServiceClient(
            account_url=self.config['account_url'],
            credential=self.config['credential']
        )
    
    async def upload_file(self, file_path: str, destination: str, metadata: Dict = None) -> Dict[str, Any]:
        """Upload de arquivo assíncrono"""
        try:
            if self.provider == 'google_drive':
                return await self._upload_google_drive(file_path, destination, metadata)
            elif self.provider == 'dropbox':
                return await self._upload_dropbox(file_path, destination, metadata)
            elif self.provider == 'onedrive':
                return await self._upload_onedrive(file_path, destination, metadata)
            elif self.provider == 'aws_s3':
                return await self._upload_s3(file_path, destination, metadata)
            elif self.provider == 'google_cloud':
                return await self._upload_google_cloud(file_path, destination, metadata)
            elif self.provider == 'azure_blob':
                return await self._upload_azure_blob(file_path, destination, metadata)
        except Exception as e:
            logger.error(f"Erro no upload para {self.provider}: {e}")
            return {'success': False, 'error': str(e)}
    
    async def _upload_google_drive(self, file_path: str, destination: str, metadata: Dict = None):
        """Upload para Google Drive"""
        file_metadata = {
            'name': destination,
            'parents': [self.config.get('folder_id', 'root')]
        }
        
        if metadata:
            file_metadata.update(metadata)
        
        media = MediaIoBaseUpload(
            open(file_path, 'rb'),
            resumable=True
        )
        
        file = self.client.files().create(
            body=file_metadata,
            media_body=media,
            fields='id,name,size,webViewLink'
        ).execute()
        
        return {
            'success': True,
            'file_id': file.get('id'),
            'name': file.get('name'),
            'size': file.get('size'),
            'url': file.get('webViewLink')
        }
    
    async def _upload_dropbox(self, file_path: str, destination: str, metadata: Dict = None):
        """Upload para Dropbox"""
        async with aiofiles.open(file_path, 'rb') as f:
            file_content = await f.read()
        
        file_size = len(file_content)
        
        # Iniciar upload session
        upload_session = self.client.files_upload_session_start(
            file_content[:8 * 1024 * 1024],  # Primeiro 8MB
            mode=dropbox.files.WriteMode.add
        )
        
        # Upload do restante
        cursor = upload_session.session_id
        offset = 8 * 1024 * 1024
        
        while offset < file_size:
            chunk_size = min(8 * 1024 * 1024, file_size - offset)
            chunk = file_content[offset:offset + chunk_size]
            
            self.client.files_upload_session_append_v2(
                chunk, cursor
            )
            
            offset += chunk_size
        
        # Finalizar upload
        file_metadata = self.client.files_upload_session_finish(
            b'', cursor, commit_info=dropbox.files.CommitInfo(path=destination)
        )
        
        return {
            'success': True,
            'file_id': file_metadata.id,
            'name': file_metadata.name,
            'size': file_metadata.size,
            'url': self.client.sharing_create_shared_link(file_metadata.path_lower).url
        }
    
    async def _upload_s3(self, file_path: str, destination: str, metadata: Dict = None):
        """Upload para AWS S3"""
        bucket_name = self.config['bucket_name']
        
        extra_args = {}
        if metadata:
            extra_args['Metadata'] = metadata
        
        self.client.upload_file(
            file_path,
            bucket_name,
            destination,
            ExtraArgs=extra_args
        )
        
        # Gerar URL
        url = f"https://{bucket_name}.s3.amazonaws.com/{destination}"
        
        return {
            'success': True,
            'file_id': destination,
            'name': destination,
            'size': os.path.getsize(file_path),
            'url': url
        }
    
    async def _upload_google_cloud(self, file_path: str, destination: str, metadata: Dict = None):
        """Upload para Google Cloud Storage"""
        bucket = self.client.bucket(self.config['bucket_name'])
        blob = bucket.blob(destination)
        
        if metadata:
            blob.metadata = metadata
        
        await asyncio.get_event_loop().run_in_executor(
            None, lambda: blob.upload_from_filename(file_path)
        )
        
        return {
            'success': True,
            'file_id': destination,
            'name': destination,
            'size': os.path.getsize(file_path),
            'url': blob.public_url
        }
    
    async def download_file(self, file_id: str, local_path: str) -> Dict[str, Any]:
        """Download de arquivo assíncrono"""
        try:
            if self.provider == 'google_drive':
                return await self._download_google_drive(file_id, local_path)
            elif self.provider == 'dropbox':
                return await self._download_dropbox(file_id, local_path)
            elif self.provider == 'aws_s3':
                return await self._download_s3(file_id, local_path)
            elif self.provider == 'google_cloud':
                return await self._download_google_cloud(file_id, local_path)
        except Exception as e:
            logger.error(f"Erro no download do {self.provider}: {e}")
            return {'success': False, 'error': str(e)}
    
    async def _download_google_drive(self, file_id: str, local_path: str):
        """Download do Google Drive"""
        request = self.client.files().get_media(fileId=file_id)
        
        with open(local_path, 'wb') as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()
                if status:
                    print(f"Download {int(status.progress() * 100)}%")
        
        return {
            'success': True,
            'local_path': local_path,
            'size': os.path.getsize(local_path)
        }
    
    async def _download_s3(self, file_id: str, local_path: str):
        """Download do AWS S3"""
        bucket_name = self.config['bucket_name']
        
        self.client.download_file(bucket_name, file_id, local_path)
        
        return {
            'success': True,
            'local_path': local_path,
            'size': os.path.getsize(local_path)
        }

class PersonalLibrary:
    """Biblioteca pessoal de audiolivros"""
    
    def __init__(self, db_path: str = 'library.db'):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Inicializa banco de dados da biblioteca"""
        import sqlite3
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Tabela de livros
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                author TEXT,
                isbn TEXT,
                publisher TEXT,
                publish_date DATE,
                genre TEXT,
                language TEXT,
                description TEXT,
                cover_image TEXT,
                file_path TEXT,
                file_size INTEGER,
                file_format TEXT,
                duration_seconds INTEGER,
                word_count INTEGER,
                pages_count INTEGER,
                reading_level TEXT,
                tags TEXT,
                rating REAL,
                date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_accessed TIMESTAMP,
                access_count INTEGER DEFAULT 0,
                is_favorite BOOLEAN DEFAULT 0,
                reading_progress REAL DEFAULT 0.0,
                notes TEXT,
                cloud_provider TEXT,
                cloud_file_id TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Tabela de capítulos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chapters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                chapter_number INTEGER NOT NULL,
                title TEXT,
                start_time INTEGER,
                end_time INTEGER,
                audio_file_path TEXT,
                text_content TEXT,
                word_count INTEGER,
                FOREIGN KEY (book_id) REFERENCES books (id)
            )
        ''')
        
        # Tabela de notas e marcadores
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bookmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                book_id INTEGER NOT NULL,
                chapter_number INTEGER,
                timestamp INTEGER,
                note TEXT,
                position_seconds INTEGER,
                page_number INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (book_id) REFERENCES books (id)
            )
        ''')
        
        # Tabela de estatísticas de leitura
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reading_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                book_id INTEGER NOT NULL,
                date DATE NOT NULL,
                minutes_read INTEGER DEFAULT 0,
                pages_read INTEGER DEFAULT 0,
                words_read INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (book_id) REFERENCES books (id)
            )
        ''')
        
        # Tabela de recomendações
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                book_id INTEGER,
                recommended_book_id INTEGER,
                recommendation_type TEXT,
                confidence_score REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (book_id) REFERENCES books (id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def add_book(self, user_id: int, book_data: Dict[str, Any]) -> int:
        """Adiciona livro à biblioteca"""
        import sqlite3
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO books (
                user_id, title, author, isbn, publisher, publish_date,
                genre, language, description, cover_image, file_path,
                file_size, file_format, duration_seconds, word_count,
                pages_count, reading_level, tags, rating,
                cloud_provider, cloud_file_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            book_data.get('title'),
            book_data.get('author'),
            book_data.get('isbn'),
            book_data.get('publisher'),
            book_data.get('publish_date'),
            book_data.get('genre'),
            book_data.get('language'),
            book_data.get('description'),
            book_data.get('cover_image'),
            book_data.get('file_path'),
            book_data.get('file_size'),
            book_data.get('file_format'),
            book_data.get('duration_seconds'),
            book_data.get('word_count'),
            book_data.get('pages_count'),
            book_data.get('reading_level'),
            json.dumps(book_data.get('tags', [])),
            book_data.get('rating'),
            book_data.get('cloud_provider'),
            book_data.get('cloud_file_id')
        ))
        
        book_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return book_id
    
    def get_user_books(self, user_id: int, filters: Dict = None) -> List[Dict[str, Any]]:
        """Obtém livros do usuário com filtros opcionais"""
        import sqlite3
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        query = "SELECT * FROM books WHERE user_id = ?"
        params = [user_id]
        
        if filters:
            if filters.get('genre'):
                query += " AND genre = ?"
                params.append(filters['genre'])
            
            if filters.get('language'):
                query += " AND language = ?"
                params.append(filters['language'])
            
            if filters.get('is_favorite'):
                query += " AND is_favorite = 1"
            
            if filters.get('rating_min'):
                query += " AND rating >= ?"
                params.append(filters['rating_min'])
        
        query += " ORDER BY date_added DESC"
        
        cursor.execute(query, params)
        books = cursor.fetchall()
        
        # Converter para lista de dicionários
        books_list = []
        for book in books:
            book_dict = {
                'id': book[0],
                'user_id': book[1],
                'title': book[2],
                'author': book[3],
                'isbn': book[4],
                'publisher': book[5],
                'publish_date': book[6],
                'genre': book[7],
                'language': book[8],
                'description': book[9],
                'cover_image': book[10],
                'file_path': book[11],
                'file_size': book[12],
                'file_format': book[13],
                'duration_seconds': book[14],
                'word_count': book[15],
                'pages_count': book[16],
                'reading_level': book[17],
                'tags': json.loads(book[18]) if book[18] else [],
                'rating': book[19],
                'date_added': book[20],
                'last_accessed': book[21],
                'access_count': book[22],
                'is_favorite': book[23],
                'reading_progress': book[24],
                'notes': book[25],
                'cloud_provider': book[26],
                'cloud_file_id': book[27]
            }
            books_list.append(book_dict)
        
        conn.close()
        return books_list
    
    def update_reading_progress(self, user_id: int, book_id: int, progress: float):
        """Atualiza progresso de leitura"""
        import sqlite3
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE books 
            SET reading_progress = ?, last_accessed = CURRENT_TIMESTAMP, access_count = access_count + 1
            WHERE id = ? AND user_id = ?
        ''', (progress, book_id, user_id))
        
        conn.commit()
        conn.close()
    
    def add_bookmark(self, user_id: int, book_id: int, bookmark_data: Dict[str, Any]):
        """Adiciona marcador ou nota"""
        import sqlite3
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO bookmarks (
                user_id, book_id, chapter_number, timestamp,
                note, position_seconds, page_number
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id, book_id,
            bookmark_data.get('chapter_number'),
            bookmark_data.get('timestamp'),
            bookmark_data.get('note'),
            bookmark_data.get('position_seconds'),
            bookmark_data.get('page_number')
        ))
        
        bookmark_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return bookmark_id
    
    def get_reading_stats(self, user_id: int, days: int = 30) -> Dict[str, Any]:
        """Obtém estatísticas de leitura"""
        import sqlite3
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Data de início
        start_date = (datetime.now() - timedelta(days=days)).date()
        
        cursor.execute('''
            SELECT 
                SUM(minutes_read) as total_minutes,
                SUM(pages_read) as total_pages,
                SUM(words_read) as total_words,
                COUNT(DISTINCT date) as reading_days
            FROM reading_stats 
            WHERE user_id = ? AND date >= ?
        ''', (user_id, start_date))
        
        stats = cursor.fetchone()
        
        conn.close()
        
        return {
            'total_minutes': stats[0] or 0,
            'total_pages': stats[1] or 0,
            'total_words': stats[2] or 0,
            'reading_days': stats[3] or 0,
            'avg_minutes_per_day': (stats[0] or 0) / max(1, stats[3] or 1),
            'period_days': days
        }
    
    def generate_recommendations(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Gera recomendações baseadas no histórico do usuário"""
        import sqlite3
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Obter gêneros e autores preferidos
        cursor.execute('''
            SELECT genre, author, COUNT(*) as count
            FROM books 
            WHERE user_id = ? AND rating >= 4.0
            GROUP BY genre, author
            ORDER BY count DESC
            LIMIT 5
        ''', (user_id,))
        
        preferences = cursor.fetchall()
        conn.close()
        
        # Gerar recomendações baseadas nas preferências
        recommendations = []
        
        for genre, author, count in preferences:
            # Aqui você poderia integrar com APIs externas
            # como Google Books API, Open Library API, etc.
            rec = {
                'type': 'genre_match',
                'genre': genre,
                'author': author,
                'confidence': min(count / 10.0, 1.0),
                'suggestion': f"Mais livros de {author} no gênero {genre}"
            }
            recommendations.append(rec)
        
        return recommendations[:limit]

# Classe para integração com APIs externas
class ExternalAPIs:
    """Integração com APIs externas de livros"""
    
    def __init__(self):
        self.google_books_api_key = os.environ.get('GOOGLE_BOOKS_API_KEY')
        self.open_library_base_url = "https://openlibrary.org"
    
    async def search_google_books(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Busca livros na Google Books API"""
        if not self.google_books_api_key:
            return []
        
        url = f"https://www.googleapis.com/books/v1/volumes"
        params = {
            'q': query,
            'maxResults': max_results,
            'key': self.google_books_api_key,
            'langRestrict': 'pt'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_google_books_results(data.get('items', []))
        
        return []
    
    def _parse_google_books_results(self, items: List[Dict]) -> List[Dict[str, Any]]:
        """Parse resultados da Google Books API"""
        books = []
        
        for item in items:
            volume_info = item.get('volumeInfo', {})
            
            book = {
                'id': item.get('id'),
                'title': volume_info.get('title', ''),
                'authors': volume_info.get('authors', []),
                'publisher': volume_info.get('publisher', ''),
                'publish_date': volume_info.get('publishedDate', ''),
                'description': volume_info.get('description', ''),
                'isbn': self._extract_isbn(volume_info.get('industryIdentifiers', [])),
                'page_count': volume_info.get('pageCount', 0),
                'categories': volume_info.get('categories', []),
                'average_rating': volume_info.get('averageRating', 0),
                'ratings_count': volume_info.get('ratingsCount', 0),
                'cover_image': self._get_cover_image(volume_info.get('imageLinks', {})),
                'preview_link': volume_info.get('previewLink', ''),
                'info_link': volume_info.get('infoLink', '')
            }
            
            books.append(book)
        
        return books
    
    def _extract_isbn(self, identifiers: List[Dict]) -> str:
        """Extrai ISBN da lista de identificadores"""
        for identifier in identifiers:
            if identifier.get('type') == 'ISBN_13':
                return identifier.get('identifier')
            elif identifier.get('type') == 'ISBN_10':
                return identifier.get('identifier')
        return ''
    
    def _get_cover_image(self, image_links: Dict) -> str:
        """Obtém URL da capa do livro"""
        # Prioridade: large > medium > small > thumbnail
        for size in ['large', 'medium', 'small', 'thumbnail']:
            if image_links.get(size):
                return image_links[size].get('href', '')
        return ''
    
    async def search_open_library(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Busca livros na Open Library API"""
        url = f"{self.open_library_base_url}/search.json"
        params = {
            'q': query,
            'limit': max_results,
            'language': 'por'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_open_library_results(data.get('docs', []))
        
        return []
    
    def _parse_open_library_results(self, docs: List[Dict]) -> List[Dict[str, Any]]:
        """Parse resultados da Open Library API"""
        books = []
        
        for doc in docs:
            book = {
                'id': doc.get('key', ''),
                'title': doc.get('title', ''),
                'authors': [author.get('name', '') for author in doc.get('author_name', [])],
                'publish_date': doc.get('first_publish_year', ''),
                'isbn': self._extract_isbn_open(doc.get('isbn', [])),
                'page_count': doc.get('number_of_pages', 0),
                'cover_image': self._get_cover_open_library(doc.get('key', '')),
                'description': doc.get('first_sentence', [''])[0] if doc.get('first_sentence') else '',
                'subjects': doc.get('subject', []),
                'info_link': f"{self.open_library_base_url}{doc.get('key', '')}"
            }
            
            books.append(book)
        
        return books
    
    def _extract_isbn_open(self, isbns: List[str]) -> str:
        """Extrai ISBN da Open Library"""
        return isbns[0] if isbns else ''
    
    def _get_cover_open_library(self, key: str) -> str:
        """Obtém URL da capa da Open Library"""
        cover_id = key.replace('/works/', '')
        return f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"

# Classe para sincronização entre dispositivos
class SyncManager:
    """Gerenciador de sincronização entre dispositivos"""
    
    def __init__(self, redis_client):
        self.redis_client = redis_client
    
    async def sync_reading_progress(self, user_id: int, book_id: int, progress: float):
        """Sincroniza progresso de leitura"""
        sync_data = {
            'user_id': user_id,
            'book_id': book_id,
            'progress': progress,
            'timestamp': datetime.utcnow().isoformat(),
            'device_id': self._get_device_id()
        }
        
        # Salvar no Redis
        sync_key = f"sync:reading_progress:{user_id}:{book_id}"
        await self.redis_client.set(sync_key, json.dumps(sync_data), ex=86400)  # 24 horas
        
        # Publicar para outros dispositivos
        channel = f"sync_channel:{user_id}"
        await self.redis_client.publish(channel, json.dumps(sync_data))
    
    async def sync_bookmarks(self, user_id: int, bookmark_data: Dict[str, Any]):
        """Sincroniza marcadores"""
        sync_data = {
            'user_id': user_id,
            'type': 'bookmark',
            'data': bookmark_data,
            'timestamp': datetime.utcnow().isoformat(),
            'device_id': self._get_device_id()
        }
        
        # Salvar no Redis
        sync_key = f"sync:bookmarks:{user_id}"
        bookmarks = await self.redis_client.get(sync_key)
        
        if bookmarks:
            bookmark_list = json.loads(bookmarks)
            bookmark_list.append(sync_data)
        else:
            bookmark_list = [sync_data]
        
        await self.redis_client.set(sync_key, json.dumps(bookmark_list), ex=86400)
        
        # Publicar para outros dispositivos
        channel = f"sync_channel:{user_id}"
        await self.redis_client.publish(channel, json.dumps(sync_data))
    
    def _get_device_id(self) -> str:
        """Gera/obtém ID único do dispositivo"""
        device_id = os.environ.get('DEVICE_ID')
        if not device_id:
            import uuid
            device_id = str(uuid.uuid4())
            os.environ['DEVICE_ID'] = device_id
        
        return device_id
    
    async def get_sync_data(self, user_id: int, sync_type: str) -> List[Dict[str, Any]]:
        """Obtém dados sincronizados"""
        sync_key = f"sync:{sync_type}:{user_id}"
        data = await self.redis_client.get(sync_key)
        
        if data:
            return json.loads(data)
        
        return []
