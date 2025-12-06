"""
Модуль конвертации файлов
Содержит все функции для преобразования форматов
"""

import io
import json
import csv
import xml.etree.ElementTree as ET
from xml.dom import minidom
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from PIL import Image
import markdown
import pandas as pd

# PDF и Word
try:
    from pypdf import PdfReader, PdfWriter
    from pdf2image import convert_from_path

    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

try:
    from docx import Document
    from docx.shared import Inches

    DOCX_SUPPORT = True
except ImportError:
    DOCX_SUPPORT = False

# Аудио
try:
    from pydub import AudioSegment

    AUDIO_SUPPORT = True
except ImportError:
    AUDIO_SUPPORT = False


class ConversionError(Exception):
    """Ошибка конвертации"""
    pass


# ═══════════════════════════════════════════════════════════════
# КОНВЕРТАЦИЯ ИЗОБРАЖЕНИЙ
# ═══════════════════════════════════════════════════════════════

class ImageConverter:
    """Конвертер изображений"""

    SUPPORTED_FORMATS = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'tiff', 'ico']

    @staticmethod
    def convert(
            input_path: Path,
            output_format: str,
            width: Optional[int] = None,
            height: Optional[int] = None,
            quality: int = 85,
            keep_aspect_ratio: bool = True
    ) -> Tuple[bytes, str]:
        """
        Конвертация изображения

        Args:
            input_path: Путь к исходному файлу
            output_format: Целевой формат (jpg, png, webp, etc.)
            width: Новая ширина (опционально)
            height: Новая высота (опционально)
            quality: Качество (1-100, для JPEG/WebP)
            keep_aspect_ratio: Сохранять пропорции

        Returns:
            Tuple[bytes, str]: Байты изображения и MIME-тип
        """
        output_format = output_format.lower()
        if output_format == 'jpg':
            output_format = 'jpeg'

        if output_format not in ['jpeg', 'png', 'gif', 'webp', 'bmp', 'tiff', 'ico']:
            raise ConversionError(f"Неподдерживаемый формат: {output_format}")

        try:
            with Image.open(input_path) as img:
                # Конвертируем в RGB для JPEG (если есть альфа-канал)
                if output_format == 'jpeg' and img.mode in ('RGBA', 'LA', 'P'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = background

                # Ресайз
                if width or height:
                    img = ImageConverter._resize(img, width, height, keep_aspect_ratio)

                # Сохраняем в байты
                buffer = io.BytesIO()

                save_kwargs = {}
                if output_format in ['jpeg', 'webp']:
                    save_kwargs['quality'] = quality
                if output_format == 'png':
                    save_kwargs['optimize'] = True

                img.save(buffer, format=output_format.upper(), **save_kwargs)
                buffer.seek(0)

                mime_types = {
                    'jpeg': 'image/jpeg',
                    'png': 'image/png',
                    'gif': 'image/gif',
                    'webp': 'image/webp',
                    'bmp': 'image/bmp',
                    'tiff': 'image/tiff',
                    'ico': 'image/x-icon'
                }

                return buffer.getvalue(), mime_types.get(output_format, 'application/octet-stream')

        except Exception as e:
            raise ConversionError(f"Ошибка конвертации изображения: {str(e)}")

    @staticmethod
    def _resize(img: Image.Image, width: Optional[int], height: Optional[int], keep_aspect_ratio: bool) -> Image.Image:
        """Изменение размера изображения"""
        original_width, original_height = img.size

        if keep_aspect_ratio:
            if width and height:
                # Вписываем в заданные размеры
                ratio = min(width / original_width, height / original_height)
                new_width = int(original_width * ratio)
                new_height = int(original_height * ratio)
            elif width:
                ratio = width / original_width
                new_width = width
                new_height = int(original_height * ratio)
            elif height:
                ratio = height / original_height
                new_width = int(original_width * ratio)
                new_height = height
            else:
                return img
        else:
            new_width = width or original_width
            new_height = height or original_height

        return img.resize((new_width, new_height), Image.Resampling.LANCZOS)

    @staticmethod
    def get_info(input_path: Path) -> Dict[str, Any]:
        """Получить информацию об изображении"""
        with Image.open(input_path) as img:
            return {
                'format': img.format,
                'mode': img.mode,
                'width': img.width,
                'height': img.height,
                'size_bytes': input_path.stat().st_size
            }

    @staticmethod
    def create_thumbnail(input_path: Path, size: Tuple[int, int] = (200, 200)) -> bytes:
        """Создать миниатюру"""
        with Image.open(input_path) as img:
            img.thumbnail(size, Image.Resampling.LANCZOS)
            buffer = io.BytesIO()

            if img.mode in ('RGBA', 'LA', 'P'):
                img.save(buffer, format='PNG')
            else:
                img.save(buffer, format='JPEG', quality=85)

            buffer.seek(0)
            return buffer.getvalue()


# ═══════════════════════════════════════════════════════════════
# КОНВЕРТАЦИЯ ДАННЫХ (CSV, JSON, XML)
# ═══════════════════════════════════════════════════════════════

class DataConverter:
    """Конвертер табличных данных"""

    @staticmethod
    def csv_to_json(input_path: Path, indent: int = 2) -> Tuple[bytes, str]:
        """CSV → JSON"""
        try:
            df = pd.read_csv(input_path)
            result = df.to_json(orient='records', indent=indent, force_ascii=False)
            return result.encode('utf-8'), 'application/json'
        except Exception as e:
            raise ConversionError(f"Ошибка конвертации CSV→JSON: {str(e)}")

    @staticmethod
    def json_to_csv(input_path: Path) -> Tuple[bytes, str]:
        """JSON → CSV"""
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if isinstance(data, dict):
                data = [data]

            df = pd.DataFrame(data)
            buffer = io.StringIO()
            df.to_csv(buffer, index=False)
            return buffer.getvalue().encode('utf-8'), 'text/csv'
        except Exception as e:
            raise ConversionError(f"Ошибка конвертации JSON→CSV: {str(e)}")

    @staticmethod
    def csv_to_xml(input_path: Path, root_name: str = 'data', row_name: str = 'row') -> Tuple[bytes, str]:
        """CSV → XML"""
        try:
            df = pd.read_csv(input_path)

            root = ET.Element(root_name)

            for _, row in df.iterrows():
                row_elem = ET.SubElement(root, row_name)
                for col_name, value in row.items():
                    col_elem = ET.SubElement(row_elem, str(col_name).replace(' ', '_'))
                    col_elem.text = str(value) if pd.notna(value) else ''

            # Форматируем XML
            xml_str = minidom.parseString(ET.tostring(root, encoding='unicode')).toprettyxml(indent='  ')

            return xml_str.encode('utf-8'), 'application/xml'
        except Exception as e:
            raise ConversionError(f"Ошибка конвертации CSV→XML: {str(e)}")

    @staticmethod
    def xml_to_csv(input_path: Path) -> Tuple[bytes, str]:
        """XML → CSV"""
        try:
            tree = ET.parse(input_path)
            root = tree.getroot()

            data = []
            for child in root:
                row = {}
                for elem in child:
                    row[elem.tag] = elem.text
                data.append(row)

            df = pd.DataFrame(data)
            buffer = io.StringIO()
            df.to_csv(buffer, index=False)
            return buffer.getvalue().encode('utf-8'), 'text/csv'
        except Exception as e:
            raise ConversionError(f"Ошибка конвертации XML→CSV: {str(e)}")

    @staticmethod
    def json_to_xml(input_path: Path, root_name: str = 'data') -> Tuple[bytes, str]:
        """JSON → XML"""
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            def dict_to_xml(d, parent):
                if isinstance(d, dict):
                    for key, value in d.items():
                        child = ET.SubElement(parent, str(key).replace(' ', '_'))
                        dict_to_xml(value, child)
                elif isinstance(d, list):
                    for item in d:
                        child = ET.SubElement(parent, 'item')
                        dict_to_xml(item, child)
                else:
                    parent.text = str(d) if d is not None else ''

            root = ET.Element(root_name)

            if isinstance(data, list):
                for item in data:
                    item_elem = ET.SubElement(root, 'item')
                    dict_to_xml(item, item_elem)
            else:
                dict_to_xml(data, root)

            xml_str = minidom.parseString(ET.tostring(root, encoding='unicode')).toprettyxml(indent='  ')

            return xml_str.encode('utf-8'), 'application/xml'
        except Exception as e:
            raise ConversionError(f"Ошибка конвертации JSON→XML: {str(e)}")

    @staticmethod
    def xml_to_json(input_path: Path, indent: int = 2) -> Tuple[bytes, str]:
        """XML → JSON"""
        try:
            tree = ET.parse(input_path)
            root = tree.getroot()

            def xml_to_dict(elem):
                result = {}
                for child in elem:
                    if len(child) > 0:
                        value = xml_to_dict(child)
                    else:
                        value = child.text

                    if child.tag in result:
                        if not isinstance(result[child.tag], list):
                            result[child.tag] = [result[child.tag]]
                        result[child.tag].append(value)
                    else:
                        result[child.tag] = value

                return result if result else elem.text

            data = {root.tag: xml_to_dict(root)}
            result = json.dumps(data, indent=indent, ensure_ascii=False)

            return result.encode('utf-8'), 'application/json'
        except Exception as e:
            raise ConversionError(f"Ошибка конвертации XML→JSON: {str(e)}")

    @staticmethod
    def csv_to_excel(input_path: Path) -> Tuple[bytes, str]:
        """CSV → Excel"""
        try:
            df = pd.read_csv(input_path)
            buffer = io.BytesIO()
            df.to_excel(buffer, index=False, engine='openpyxl')
            buffer.seek(0)
            return buffer.getvalue(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        except Exception as e:
            raise ConversionError(f"Ошибка конвертации CSV→Excel: {str(e)}")

    @staticmethod
    def excel_to_csv(input_path: Path) -> Tuple[bytes, str]:
        """Excel → CSV"""
        try:
            df = pd.read_excel(input_path, engine='openpyxl')
            buffer = io.StringIO()
            df.to_csv(buffer, index=False)
            return buffer.getvalue().encode('utf-8'), 'text/csv'
        except Exception as e:
            raise ConversionError(f"Ошибка конвертации Excel→CSV: {str(e)}")


# ═══════════════════════════════════════════════════════════════
# КОНВЕРТАЦИЯ ДОКУМЕНТОВ
# ═══════════════════════════════════════════════════════════════

class DocumentConverter:
    """Конвертер документов"""

    @staticmethod
    def markdown_to_html(input_path: Path, full_page: bool = True) -> Tuple[bytes, str]:
        """Markdown → HTML"""
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                md_content = f.read()

            # Конвертируем Markdown в HTML
            html_content = markdown.markdown(
                md_content,
                extensions=['tables', 'fenced_code', 'codehilite', 'toc']
            )

            if full_page:
                html_content = f'''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Converted Document</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 40px 20px;
            line-height: 1.6;
            color: #333;
        }}
        h1, h2, h3 {{ color: #2c3e50; margin-top: 1.5em; }}
        code {{
            background: #f4f4f4;
            padding: 2px 6px;
            border-radius: 4px;
            font-family: 'Consolas', monospace;
        }}
        pre {{
            background: #2d2d2d;
            color: #f8f8f2;
            padding: 16px;
            border-radius: 8px;
            overflow-x: auto;
        }}
        pre code {{ background: none; color: inherit; }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 1em 0;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 8px 12px;
            text-align: left;
        }}
        th {{ background: #f5f5f5; }}
        blockquote {{
            border-left: 4px solid #3498db;
            margin: 1em 0;
            padding: 0.5em 1em;
            background: #f9f9f9;
        }}
        a {{ color: #3498db; }}
        img {{ max-width: 100%; height: auto; }}
    </style>
</head>
<body>
{html_content}
</body>
</html>'''

            return html_content.encode('utf-8'), 'text/html'
        except Exception as e:
            raise ConversionError(f"Ошибка конвертации MD→HTML: {str(e)}")

    @staticmethod
    def html_to_markdown(input_path: Path) -> Tuple[bytes, str]:
        """HTML → Markdown (простая конвертация)"""
        try:
            import re

            with open(input_path, 'r', encoding='utf-8') as f:
                html = f.read()

            # Простые замены
            conversions = [
                (r'<h1[^>]*>(.*?)</h1>', r'# \1\n'),
                (r'<h2[^>]*>(.*?)</h2>', r'## \1\n'),
                (r'<h3[^>]*>(.*?)</h3>', r'### \1\n'),
                (r'<h4[^>]*>(.*?)</h4>', r'#### \1\n'),
                (r'<strong[^>]*>(.*?)</strong>', r'**\1**'),
                (r'<b[^>]*>(.*?)</b>', r'**\1**'),
                (r'<em[^>]*>(.*?)</em>', r'*\1*'),
                (r'<i[^>]*>(.*?)</i>', r'*\1*'),
                (r'<code[^>]*>(.*?)</code>', r'`\1`'),
                (r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r'[\2](\1)'),
                (r'<img[^>]*src="([^"]*)"[^>]*alt="([^"]*)"[^>]*/?\s*>', r'![\2](\1)'),
                (r'<br\s*/?>', '\n'),
                (r'<p[^>]*>(.*?)</p>', r'\1\n\n'),
                (r'<li[^>]*>(.*?)</li>', r'- \1\n'),
                (r'<[^>]+>', ''),  # Удаляем остальные теги
            ]

            md = html
            for pattern, replacement in conversions:
                md = re.sub(pattern, replacement, md, flags=re.DOTALL | re.IGNORECASE)

            # Убираем лишние пробелы
            md = re.sub(r'\n{3,}', '\n\n', md)
            md = md.strip()

            return md.encode('utf-8'), 'text/markdown'
        except Exception as e:
            raise ConversionError(f"Ошибка конвертации HTML→MD: {str(e)}")

    @staticmethod
    def txt_to_html(input_path: Path) -> Tuple[bytes, str]:
        """TXT → HTML"""
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                text = f.read()

            # Экранируем HTML
            text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

            # Заменяем переносы строк
            text = text.replace('\n', '<br>\n')

            html = f'''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Text Document</title>
    <style>
        body {{
            font-family: 'Consolas', monospace;
            max-width: 800px;
            margin: 40px auto;
            padding: 20px;
            line-height: 1.6;
            white-space: pre-wrap;
        }}
    </style>
</head>
<body>
{text}
</body>
</html>'''

            return html.encode('utf-8'), 'text/html'
        except Exception as e:
            raise ConversionError(f"Ошибка конвертации TXT→HTML: {str(e)}")

    @staticmethod
    def txt_to_pdf(input_path: Path) -> Tuple[bytes, str]:
        """TXT → PDF (через HTML)"""
        try:
            from weasyprint import HTML

            html_bytes, _ = DocumentConverter.txt_to_html(input_path)
            html_str = html_bytes.decode('utf-8')

            pdf_bytes = HTML(string=html_str).write_pdf()

            return pdf_bytes, 'application/pdf'
        except ImportError:
            raise ConversionError("WeasyPrint не установлен. Установите: pip install weasyprint")
        except Exception as e:
            raise ConversionError(f"Ошибка конвертации TXT→PDF: {str(e)}")

    @staticmethod
    def markdown_to_pdf(input_path: Path) -> Tuple[bytes, str]:
        """Markdown → PDF"""
        try:
            from weasyprint import HTML

            html_bytes, _ = DocumentConverter.markdown_to_html(input_path)
            html_str = html_bytes.decode('utf-8')

            pdf_bytes = HTML(string=html_str).write_pdf()

            return pdf_bytes, 'application/pdf'
        except ImportError:
            raise ConversionError("WeasyPrint не установлен. Установите: pip install weasyprint")
        except Exception as e:
            raise ConversionError(f"Ошибка конвертации MD→PDF: {str(e)}")


# ═══════════════════════════════════════════════════════════════
# КОНВЕРТАЦИЯ АУДИО
# ═══════════════════════════════════════════════════════════════

class AudioConverter:
    """Конвертер аудио файлов"""

    SUPPORTED_FORMATS = ['mp3', 'wav', 'ogg', 'flac']

    @staticmethod
    def convert(
            input_path: Path,
            output_format: str,
            bitrate: str = '192k'
    ) -> Tuple[bytes, str]:
        """Конвертация аудио"""
        if not AUDIO_SUPPORT:
            raise ConversionError("pydub не установлен. Установите: pip install pydub")

        output_format = output_format.lower()

        if output_format not in AudioConverter.SUPPORTED_FORMATS:
            raise ConversionError(f"Неподдерживаемый формат: {output_format}")

        try:
            # Определяем формат входного файла
            input_format = input_path.suffix[1:].lower()

            # Загружаем аудио
            audio = AudioSegment.from_file(str(input_path), format=input_format)

            # Конвертируем
            buffer = io.BytesIO()

            export_params = {}
            if output_format == 'mp3':
                export_params['bitrate'] = bitrate

            audio.export(buffer, format=output_format, **export_params)
            buffer.seek(0)

            mime_types = {
                'mp3': 'audio/mpeg',
                'wav': 'audio/wav',
                'ogg': 'audio/ogg',
                'flac': 'audio/flac'
            }

            return buffer.getvalue(), mime_types.get(output_format, 'audio/mpeg')

        except Exception as e:
            raise ConversionError(f"Ошибка конвертации аудио: {str(e)}")

    @staticmethod
    def get_info(input_path: Path) -> Dict[str, Any]:
        """Получить информацию об аудио"""
        if not AUDIO_SUPPORT:
            return {'error': 'pydub не установлен'}

        try:
            input_format = input_path.suffix[1:].lower()
            audio = AudioSegment.from_file(str(input_path), format=input_format)

            return {
                'duration_seconds': len(audio) / 1000,
                'channels': audio.channels,
                'sample_rate': audio.frame_rate,
                'size_bytes': input_path.stat().st_size
            }
        except Exception as e:
            return {'error': str(e)}


# ═══════════════════════════════════════════════════════════════
# ГЛАВНЫЙ КОНВЕРТЕР
# ═══════════════════════════════════════════════════════════════

class FileConverter:
    """Универсальный конвертер файлов"""

    # Маппинг конвертаций: (input_format, output_format) -> converter_function
    CONVERSIONS = {
        # Изображения
        ('jpg', 'png'): lambda p, **kw: ImageConverter.convert(p, 'png', **kw),
        ('jpeg', 'png'): lambda p, **kw: ImageConverter.convert(p, 'png', **kw),
        ('png', 'jpg'): lambda p, **kw: ImageConverter.convert(p, 'jpeg', **kw),
        ('png', 'jpeg'): lambda p, **kw: ImageConverter.convert(p, 'jpeg', **kw),
        ('png', 'webp'): lambda p, **kw: ImageConverter.convert(p, 'webp', **kw),
        ('jpg', 'webp'): lambda p, **kw: ImageConverter.convert(p, 'webp', **kw),
        ('jpeg', 'webp'): lambda p, **kw: ImageConverter.convert(p, 'webp', **kw),
        ('webp', 'png'): lambda p, **kw: ImageConverter.convert(p, 'png', **kw),
        ('webp', 'jpg'): lambda p, **kw: ImageConverter.convert(p, 'jpeg', **kw),
        ('gif', 'png'): lambda p, **kw: ImageConverter.convert(p, 'png', **kw),
        ('bmp', 'png'): lambda p, **kw: ImageConverter.convert(p, 'png', **kw),
        ('bmp', 'jpg'): lambda p, **kw: ImageConverter.convert(p, 'jpeg', **kw),
        ('tiff', 'png'): lambda p, **kw: ImageConverter.convert(p, 'png', **kw),
        ('tiff', 'jpg'): lambda p, **kw: ImageConverter.convert(p, 'jpeg', **kw),
        ('png', 'ico'): lambda p, **kw: ImageConverter.convert(p, 'ico', **kw),
        ('jpg', 'ico'): lambda p, **kw: ImageConverter.convert(p, 'ico', **kw),

        # Данные
        ('csv', 'json'): lambda p, **kw: DataConverter.csv_to_json(p),
        ('json', 'csv'): lambda p, **kw: DataConverter.json_to_csv(p),
        ('csv', 'xml'): lambda p, **kw: DataConverter.csv_to_xml(p),
        ('xml', 'csv'): lambda p, **kw: DataConverter.xml_to_csv(p),
        ('json', 'xml'): lambda p, **kw: DataConverter.json_to_xml(p),
        ('xml', 'json'): lambda p, **kw: DataConverter.xml_to_json(p),
        ('csv', 'xlsx'): lambda p, **kw: DataConverter.csv_to_excel(p),
        ('xlsx', 'csv'): lambda p, **kw: DataConverter.excel_to_csv(p),
        ('xls', 'csv'): lambda p, **kw: DataConverter.excel_to_csv(p),

        # Документы
        ('md', 'html'): lambda p, **kw: DocumentConverter.markdown_to_html(p),
        ('markdown', 'html'): lambda p, **kw: DocumentConverter.markdown_to_html(p),
        ('html', 'md'): lambda p, **kw: DocumentConverter.html_to_markdown(p),
        ('html', 'markdown'): lambda p, **kw: DocumentConverter.html_to_markdown(p),
        ('txt', 'html'): lambda p, **kw: DocumentConverter.txt_to_html(p),
        ('txt', 'pdf'): lambda p, **kw: DocumentConverter.txt_to_pdf(p),
        ('md', 'pdf'): lambda p, **kw: DocumentConverter.markdown_to_pdf(p),
        ('markdown', 'pdf'): lambda p, **kw: DocumentConverter.markdown_to_pdf(p),

        # Аудио
        ('mp3', 'wav'): lambda p, **kw: AudioConverter.convert(p, 'wav'),
        ('wav', 'mp3'): lambda p, **kw: AudioConverter.convert(p, 'mp3'),
        ('ogg', 'mp3'): lambda p, **kw: AudioConverter.convert(p, 'mp3'),
        ('flac', 'mp3'): lambda p, **kw: AudioConverter.convert(p, 'mp3'),
        ('mp3', 'ogg'): lambda p, **kw: AudioConverter.convert(p, 'ogg'),
        ('wav', 'ogg'): lambda p, **kw: AudioConverter.convert(p, 'ogg'),
        ('flac', 'wav'): lambda p, **kw: AudioConverter.convert(p, 'wav'),
    }

    @classmethod
    def get_supported_conversions(cls) -> List[Dict[str, str]]:
        """Получить список поддерживаемых конвертаций"""
        return [
            {'from': k[0], 'to': k[1]}
            for k in cls.CONVERSIONS.keys()
        ]

    @classmethod
    def can_convert(cls, from_format: str, to_format: str) -> bool:
        """Проверить, поддерживается ли конвертация"""
        return (from_format.lower(), to_format.lower()) in cls.CONVERSIONS

    @classmethod
    def convert(cls, input_path: Path, output_format: str, **kwargs) -> Tuple[bytes, str]:
        """
        Универсальная конвертация

        Args:
            input_path: Путь к файлу
            output_format: Целевой формат
            **kwargs: Дополнительные параметры

        Returns:
            Tuple[bytes, str]: Байты результата и MIME-тип
        """
        input_format = input_path.suffix[1:].lower()
        output_format = output_format.lower()

        key = (input_format, output_format)

        if key not in cls.CONVERSIONS:
            raise ConversionError(
                f"Конвертация {input_format.upper()} → {output_format.upper()} не поддерживается"
            )

        converter = cls.CONVERSIONS[key]
        return converter(input_path, **kwargs)