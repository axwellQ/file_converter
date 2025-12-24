"""
Конфигурация приложения
"""

import os
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"

UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# Лимиты
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
ALLOWED_EXTENSIONS = {
    'image': ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'tiff'],
    'document': ['pdf', 'docx', 'doc', 'txt', 'md', 'html'],
    'data': ['csv', 'json', 'xml', 'xlsx', 'xls'],
    'audio': ['mp3', 'wav', 'ogg', 'flac', 'm4a'],
    'video': ['mp4', 'avi', 'mkv', 'mov', 'webm']
}

# Время жизни файлов (в секундах)
FILE_LIFETIME = 3600  # 1 час

def get_file_extension(filename: str) -> str:
    """Получить расширение файла"""
    return filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''

def generate_filename(original: str, new_extension: str) -> str:
    """Генерация уникального имени файла"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    base_name = Path(original).stem
    return f"{base_name}_{timestamp}.{new_extension}"

def get_file_category(extension: str) -> str:
    """Определить категорию файла по расширению"""
    for category, extensions in ALLOWED_EXTENSIONS.items():
        if extension in extensions:
            return category
    return 'unknown'
