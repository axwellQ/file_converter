"""
File Converter API
REST API для конвертации файлов различных форматов

Запуск: python main.py
Документация: http://localhost:8000/docs
"""

import os
import uuid
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, UploadFile, HTTPException, Query, BackgroundTasks
from fastapi.responses import Response, HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import UPLOAD_DIR, OUTPUT_DIR, MAX_FILE_SIZE, get_file_extension, generate_filename
from converters import FileConverter, ImageConverter, DataConverter, DocumentConverter, AudioConverter, ConversionError


# ═══════════════════════════════════════════════════════════════
# PYDANTIC МОДЕЛИ
# ═══════════════════════════════════════════════════════════════

class ConversionRequest(BaseModel):
    output_format: str
    width: Optional[int] = None
    height: Optional[int] = None
    quality: Optional[int] = 85

class ConversionResponse(BaseModel):
    success: bool
    message: str
    download_url: Optional[str] = None
    original_filename: str
    converted_filename: Optional[str] = None
    file_size: Optional[int] = None

class SupportedConversion(BaseModel):
    from_format: str
    to_format: str

class FileInfo(BaseModel):
    filename: str
    size_bytes: int
    format: str
    details: Dict[str, Any]


# ═══════════════════════════════════════════════════════════════
# ХРАНИЛИЩЕ ЗАДАЧ
# ═══════════════════════════════════════════════════════════════

conversion_tasks: Dict[str, Dict[str, Any]] = {}

def cleanup_old_files():
    """Очистка старых файлов"""
    import time
    current_time = time.time()

    for directory in [UPLOAD_DIR, OUTPUT_DIR]:
        for file in directory.iterdir():
            if file.is_file():
                age = current_time - file.stat().st_mtime
                if age > 3600:  # Старше 1 часа
                    try:
                        file.unlink()
                    except:
                        pass


# ═══════════════════════════════════════════════════════════════
# FASTAPI ПРИЛОЖЕНИЕ
# ═══════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle события"""
    print("🚀 File Converter API запущен")
    print("📖 Документация: http://localhost:8000/docs")
    cleanup_old_files()
    yield
    print("👋 Сервер остановлен")


app = FastAPI(
    title="🔄 File Converter API",
    description="""
## API для конвертации файлов

### Поддерживаемые форматы:

**📷 Изображения:**
- JPG ↔ PNG ↔ WebP ↔ GIF ↔ BMP ↔ TIFF ↔ ICO

**📊 Данные:**
- CSV ↔ JSON ↔ XML
- CSV → Excel (XLSX)
- Excel → CSV

**📝 Документы:**
- Markdown → HTML / PDF
- HTML → Markdown
- TXT → HTML / PDF

**🎵 Аудио:**
- MP3 ↔ WAV ↔ OGG ↔ FLAC

### Особенности:
- Изменение размера изображений
- Настройка качества сжатия
- Асинхронная обработка
    """,
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════
# HTML ИНТЕРФЕЙС
# ═══════════════════════════════════════════════════════════════

HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🔄 File Converter</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #fff;
            padding: 40px 20px;
        }
        
        .container {
            max-width: 900px;
            margin: 0 auto;
        }
        
        header {
            text-align: center;
            margin-bottom: 40px;
        }
        
        h1 {
            font-size: 2.5rem;
            margin-bottom: 10px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .subtitle {
            color: #888;
            font-size: 1.1rem;
        }
        
        .card {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 16px;
            padding: 30px;
            margin-bottom: 24px;
            backdrop-filter: blur(10px);
        }
        
        .card h2 {
            font-size: 1.3rem;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .upload-area {
            border: 2px dashed rgba(255, 255, 255, 0.2);
            border-radius: 12px;
            padding: 40px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s;
            margin-bottom: 20px;
        }
        
        .upload-area:hover {
            border-color: #667eea;
            background: rgba(102, 126, 234, 0.1);
        }
        
        .upload-area.dragover {
            border-color: #667eea;
            background: rgba(102, 126, 234, 0.2);
        }
        
        .upload-icon {
            font-size: 48px;
            margin-bottom: 16px;
        }
        
        .upload-text {
            font-size: 1.1rem;
            margin-bottom: 8px;
        }
        
        .upload-hint {
            color: #888;
            font-size: 0.9rem;
        }
        
        input[type="file"] {
            display: none;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        label {
            display: block;
            font-size: 0.9rem;
            color: #aaa;
            margin-bottom: 8px;
        }
        
        select, input[type="number"] {
            width: 100%;
            padding: 12px 16px;
            background: rgba(0, 0, 0, 0.3);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            color: #fff;
            font-size: 1rem;
            outline: none;
            transition: 0.2s;
        }
        
        select:focus, input[type="number"]:focus {
            border-color: #667eea;
        }
        
        .options-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 16px;
        }
        
        .btn {
            width: 100%;
            padding: 16px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border: none;
            border-radius: 10px;
            color: #fff;
            font-size: 1.1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(102, 126, 234, 0.3);
        }
        
        .btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none;
        }
        
        .result {
            display: none;
            padding: 20px;
            border-radius: 10px;
            margin-top: 20px;
        }
        
        .result.success {
            display: block;
            background: rgba(16, 185, 129, 0.2);
            border: 1px solid rgba(16, 185, 129, 0.3);
        }
        
        .result.error {
            display: block;
            background: rgba(239, 68, 68, 0.2);
            border: 1px solid rgba(239, 68, 68, 0.3);
        }
        
        .download-btn {
            display: inline-block;
            padding: 12px 24px;
            background: #10b981;
            color: #fff;
            text-decoration: none;
            border-radius: 8px;
            margin-top: 12px;
            font-weight: 500;
        }
        
        .download-btn:hover {
            background: #059669;
        }
        
        .supported {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 16px;
        }
        
        .format-tag {
            padding: 6px 12px;
            background: rgba(102, 126, 234, 0.2);
            border-radius: 20px;
            font-size: 0.85rem;
            color: #a5b4fc;
        }
        
        .file-info {
            background: rgba(0, 0, 0, 0.2);
            padding: 16px;
            border-radius: 8px;
            margin-bottom: 20px;
            display: none;
        }
        
        .file-info.show {
            display: block;
        }
        
        .file-info p {
            margin: 4px 0;
            font-size: 0.9rem;
            color: #aaa;
        }
        
        .file-info .filename {
            color: #fff;
            font-weight: 500;
        }
        
        .loading {
            display: none;
            text-align: center;
            padding: 20px;
        }
        
        .loading.show {
            display: block;
        }
        
        .spinner {
            width: 40px;
            height: 40px;
            border: 3px solid rgba(255, 255, 255, 0.1);
            border-top-color: #667eea;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 0 auto 16px;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        footer {
            text-align: center;
            margin-top: 40px;
            color: #666;
        }
        
        footer a {
            color: #667eea;
            text-decoration: none;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🔄 File Converter</h1>
            <p class="subtitle">Конвертируйте файлы в различные форматы онлайн</p>
        </header>
        
        <div class="card">
            <h2>📁 Загрузить файл</h2>
            
            <div class="upload-area" id="uploadArea">
                <div class="upload-icon">📤</div>
                <div class="upload-text">Перетащите файл сюда или нажмите для выбора</div>
                <div class="upload-hint">Максимальный размер: 50 MB</div>
            </div>
            <input type="file" id="fileInput">
            
            <div class="file-info" id="fileInfo">
                <p><span class="filename" id="fileName"></span></p>
                <p>Размер: <span id="fileSize"></span></p>
                <p>Формат: <span id="fileFormat"></span></p>
            </div>
            
            <div class="form-group">
                <label>Конвертировать в:</label>
                <select id="outputFormat">
                    <option value="">-- Выберите формат --</option>
                </select>
            </div>
            
            <div class="options-grid" id="imageOptions" style="display: none;">
                <div class="form-group">
                    <label>Ширина (px)</label>
                    <input type="number" id="width" placeholder="Авто">
                </div>
                <div class="form-group">
                    <label>Высота (px)</label>
                    <input type="number" id="height" placeholder="Авто">
                </div>
                <div class="form-group">
                    <label>Качество (%)</label>
                    <input type="number" id="quality" value="85" min="1" max="100">
                </div>
            </div>
            
            <button class="btn" id="convertBtn" disabled>Конвертировать</button>
            
            <div class="loading" id="loading">
                <div class="spinner"></div>
                <p>Конвертация...</p>
            </div>
            
            <div class="result" id="result"></div>
        </div>
        
        <div class="card">
            <h2>📋 Поддерживаемые форматы</h2>
            
            <p style="color: #888; margin-bottom: 12px;"><strong>📷 Изображения:</strong></p>
            <div class="supported">
                <span class="format-tag">JPG → PNG</span>
                <span class="format-tag">PNG → JPG</span>
                <span class="format-tag">PNG → WebP</span>
                <span class="format-tag">WebP → PNG</span>
                <span class="format-tag">GIF → PNG</span>
                <span class="format-tag">BMP → PNG/JPG</span>
            </div>
            
            <p style="color: #888; margin: 16px 0 12px;"><strong>📊 Данные:</strong></p>
            <div class="supported">
                <span class="format-tag">CSV → JSON</span>
                <span class="format-tag">JSON → CSV</span>
                <span class="format-tag">CSV → XML</span>
                <span class="format-tag">XML → CSV</span>
                <span class="format-tag">CSV → Excel</span>
            </div>
            
            <p style="color: #888; margin: 16px 0 12px;"><strong>📝 Документы:</strong></p>
            <div class="supported">
                <span class="format-tag">Markdown → HTML</span>
                <span class="format-tag">Markdown → PDF</span>
                <span class="format-tag">HTML → Markdown</span>
                <span class="format-tag">TXT → PDF</span>
            </div>
            
            <p style="color: #888; margin: 16px 0 12px;"><strong>🎵 Аудио:</strong></p>
            <div class="supported">
                <span class="format-tag">MP3 → WAV</span>
                <span class="format-tag">WAV → MP3</span>
                <span class="format-tag">OGG → MP3</span>
                <span class="format-tag">FLAC → MP3</span>
            </div>
        </div>
        
        <footer>
            <p>API документация: <a href="/docs">/docs</a> | <a href="/redoc">/redoc</a></p>
        </footer>
    </div>
    
    <script>
        const uploadArea = document.getElementById('uploadArea');
        const fileInput = document.getElementById('fileInput');
        const fileInfo = document.getElementById('fileInfo');
        const outputFormat = document.getElementById('outputFormat');
        const convertBtn = document.getElementById('convertBtn');
        const result = document.getElementById('result');
        const loading = document.getElementById('loading');
        const imageOptions = document.getElementById('imageOptions');
        
        let currentFile = null;
        
        // Форматы конвертации
        const conversions = {
            'jpg': ['png', 'webp', 'ico'],
            'jpeg': ['png', 'webp', 'ico'],
            'png': ['jpg', 'webp', 'ico'],
            'gif': ['png'],
            'webp': ['png', 'jpg'],
            'bmp': ['png', 'jpg'],
            'tiff': ['png', 'jpg'],
            'csv': ['json', 'xml', 'xlsx'],
            'json': ['csv', 'xml'],
            'xml': ['csv', 'json'],
            'xlsx': ['csv'],
            'xls': ['csv'],
            'md': ['html', 'pdf'],
            'markdown': ['html', 'pdf'],
            'html': ['md'],
            'txt': ['html', 'pdf'],
            'mp3': ['wav', 'ogg'],
            'wav': ['mp3', 'ogg'],
            'ogg': ['mp3', 'wav'],
            'flac': ['mp3', 'wav']
        };
        
        // Drag & Drop
        uploadArea.addEventListener('click', () => fileInput.click());
        
        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.classList.add('dragover');
        });
        
        uploadArea.addEventListener('dragleave', () => {
            uploadArea.classList.remove('dragover');
        });
        
        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('dragover');
            const files = e.dataTransfer.files;
            if (files.length) handleFile(files[0]);
        });
        
        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length) handleFile(e.target.files[0]);
        });
        
        function handleFile(file) {
            currentFile = file;
            
            // Показываем информацию
            document.getElementById('fileName').textContent = file.name;
            document.getElementById('fileSize').textContent = formatBytes(file.size);
            
            const ext = file.name.split('.').pop().toLowerCase();
            document.getElementById('fileFormat').textContent = ext.toUpperCase();
            fileInfo.classList.add('show');
            
            // Обновляем доступные форматы
            outputFormat.innerHTML = '<option value="">-- Выберите формат --</option>';
            
            const available = conversions[ext] || [];
            available.forEach(fmt => {
                const option = document.createElement('option');
                option.value = fmt;
                option.textContent = fmt.toUpperCase();
                outputFormat.appendChild(option);
            });
            
            // Показываем опции для изображений
            const imageFormats = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'tiff'];
            imageOptions.style.display = imageFormats.includes(ext) ? 'grid' : 'none';
            
            convertBtn.disabled = true;
            result.className = 'result';
            result.innerHTML = '';
        }
        
        outputFormat.addEventListener('change', () => {
            convertBtn.disabled = !outputFormat.value || !currentFile;
        });
        
        convertBtn.addEventListener('click', async () => {
            if (!currentFile || !outputFormat.value) return;
            
            convertBtn.disabled = true;
            loading.classList.add('show');
            result.className = 'result';
            
            const formData = new FormData();
            formData.append('file', currentFile);
            
            let url = `/convert?output_format=${outputFormat.value}`;
            
            const width = document.getElementById('width').value;
            const height = document.getElementById('height').value;
            const quality = document.getElementById('quality').value;
            
            if (width) url += `&width=${width}`;
            if (height) url += `&height=${height}`;
            if (quality) url += `&quality=${quality}`;
            
            try {
                const response = await fetch(url, {
                    method: 'POST',
                    body: formData
                });
                
                loading.classList.remove('show');
                
                if (response.ok) {
                    const data = await response.json();
                    result.className = 'result success';
                    result.innerHTML = `
                        <p>✅ ${data.message}</p>
                        <p>Размер: ${formatBytes(data.file_size)}</p>
                        <a href="${data.download_url}" class="download-btn" download>📥 Скачать ${data.converted_filename}</a>
                    `;
                } else {
                    const error = await response.json();
                    result.className = 'result error';
                    result.innerHTML = `<p>❌ Ошибка: ${error.detail}</p>`;
                }
            } catch (err) {
                loading.classList.remove('show');
                result.className = 'result error';
                result.innerHTML = `<p>❌ Ошибка: ${err.message}</p>`;
            }
            
            convertBtn.disabled = false;
        });
        
        function formatBytes(bytes) {
            if (bytes === 0) return '0 Bytes';
            const k = 1024;
            const sizes = ['Bytes', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }
    </script>
</body>
</html>'''


# ═══════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def home():
    """Главная страница с веб-интерфейсом"""
    return HTML_TEMPLATE


@app.get("/api/formats", response_model=List[SupportedConversion])
async def get_supported_formats():
    """Получить список поддерживаемых конвертаций"""
    conversions = FileConverter.get_supported_conversions()
    return [SupportedConversion(from_format=c['from'], to_format=c['to']) for c in conversions]


@app.post("/convert", response_model=ConversionResponse)
async def convert_file(
    file: UploadFile = File(...),
    output_format: str = Query(..., description="Целевой формат"),
    width: Optional[int] = Query(None, description="Ширина (для изображений)"),
    height: Optional[int] = Query(None, description="Высота (для изображений)"),
    quality: int = Query(85, ge=1, le=100, description="Качество (для JPEG/WebP)")
):
    """
    Конвертировать файл

    - **file**: Файл для конвертации
    - **output_format**: Целевой формат (например: png, jpg, pdf, json)
    - **width**: Новая ширина (только для изображений)
    - **height**: Новая высота (только для изображений)
    - **quality**: Качество сжатия 1-100 (для JPEG, WebP)
    """
    # Проверяем размер файла
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, f"Файл слишком большой. Максимум: {MAX_FILE_SIZE // 1024 // 1024} MB")

    # Получаем расширение
    input_ext = get_file_extension(file.filename)
    output_format = output_format.lower().strip('.')

    # Проверяем возможность конвертации
    if not FileConverter.can_convert(input_ext, output_format):
        raise HTTPException(
            400,
            f"Конвертация {input_ext.upper()} → {output_format.upper()} не поддерживается"
        )

    # Сохраняем входной файл
    input_filename = f"{uuid.uuid4()}_{file.filename}"
    input_path = UPLOAD_DIR / input_filename

    with open(input_path, 'wb') as f:
        f.write(content)

    try:
        # Конвертируем
        result_bytes, mime_type = FileConverter.convert(
            input_path,
            output_format,
            width=width,
            height=height,
            quality=quality
        )

        # Сохраняем результат
        output_filename = generate_filename(file.filename, output_format)
        output_path = OUTPUT_DIR / output_filename

        with open(output_path, 'wb') as f:
            f.write(result_bytes)

        return ConversionResponse(
            success=True,
            message=f"Файл успешно конвертирован в {output_format.upper()}",
            download_url=f"/download/{output_filename}",
            original_filename=file.filename,
            converted_filename=output_filename,
            file_size=len(result_bytes)
        )

    except ConversionError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Внутренняя ошибка: {str(e)}")
    finally:
        # Удаляем входной файл
        try:
            input_path.unlink()
        except:
            pass


@app.get("/download/{filename}")
async def download_file(filename: str):
    """Скачать сконвертированный файл"""
    file_path = OUTPUT_DIR / filename

    if not file_path.exists():
        raise HTTPException(404, "Файл не найден")

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type='application/octet-stream'
    )


@app.post("/api/image/info", response_model=FileInfo)
async def get_image_info(file: UploadFile = File(...)):
    """Получить информацию об изображении"""
    content = await file.read()

    input_filename = f"{uuid.uuid4()}_{file.filename}"
    input_path = UPLOAD_DIR / input_filename

    with open(input_path, 'wb') as f:
        f.write(content)

    try:
        info = ImageConverter.get_info(input_path)
        return FileInfo(
            filename=file.filename,
            size_bytes=len(content),
            format=info['format'],
            details=info
        )
    finally:
        try:
            input_path.unlink()
        except:
            pass


@app.post("/api/image/thumbnail")
async def create_thumbnail(
    file: UploadFile = File(...),
    size: int = Query(200, ge=50, le=500)
):
    """Создать миниатюру изображения"""
    content = await file.read()

    input_filename = f"{uuid.uuid4()}_{file.filename}"
    input_path = UPLOAD_DIR / input_filename

    with open(input_path, 'wb') as f:
        f.write(content)

    try:
        thumbnail = ImageConverter.create_thumbnail(input_path, (size, size))
        return Response(content=thumbnail, media_type='image/png')
    except Exception as e:
        raise HTTPException(400, str(e))
    finally:
        try:
            input_path.unlink()
        except:
            pass


@app.post("/api/image/resize")
async def resize_image(
    file: UploadFile = File(...),
    width: Optional[int] = Query(None),
    height: Optional[int] = Query(None),
    keep_aspect_ratio: bool = Query(True)
):
    """Изменить размер изображения"""
    if not width and not height:
        raise HTTPException(400, "Укажите width или height")

    content = await file.read()

    input_filename = f"{uuid.uuid4()}_{file.filename}"
    input_path = UPLOAD_DIR / input_filename

    with open(input_path, 'wb') as f:
        f.write(content)

    try:
        ext = get_file_extension(file.filename)
        result, mime_type = ImageConverter.convert(
            input_path, ext,
            width=width, height=height,
            keep_aspect_ratio=keep_aspect_ratio
        )
        return Response(content=result, media_type=mime_type)
    except ConversionError as e:
        raise HTTPException(400, str(e))
    finally:
        try:
            input_path.unlink()
        except:
            pass


# ═══════════════════════════════════════════════════════════════
# ЗАПУСК
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    print("""
╔═══════════════════════════════════════════════════════════════════╗
║                                                                   ║
║   🔄 File Converter API                                           ║
║                                                                   ║
║   Веб-интерфейс: http://localhost:8000                            ║
║   API документация: http://localhost:8000/docs                    ║
║   ReDoc: http://localhost:8000/redoc                              ║
║                                                                   ║
║   Нажмите Ctrl+C для остановки                                    ║
║                                                                   ║
╚═══════════════════════════════════════════════════════════════════╝
    """)

    uvicorn.run(app, host="0.0.0.0", port=8000)