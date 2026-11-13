import os
import re
from pathlib import Path
from typing import Tuple, Dict, Any
import pymupdf as fitz  # PyMuPDF

from backend.config import Config


LANGUAGE_MAP = {
    "inglés": "en",
    "ingles": "en",
    "english": "en",
    "en": "en",
    "español": "es",
    "espanol": "es",
    "spanish": "es",
    "es": "es",
}

LANGUAGE_NAMES = {
    "en": "Inglés",
    "es": "Español",
}


class ValidationError(Exception):
    """Excepción controlada para errores de validación de entrada."""

    def __init__(self, message: str, status_code: int = 400, code: str = "VALIDATION_ERROR"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


def normalize_language(lang_raw: str) -> str:
    """Convierte el nombre o código de idioma a 'en' o 'es'."""
    if not lang_raw or not isinstance(lang_raw, str):
        raise ValidationError("Debe especificar los idiomas de origen y destino.", 400, "INVALID_LANGUAGE")
    cleaned = lang_raw.strip().lower()
    if cleaned not in LANGUAGE_MAP:
        raise ValidationError(
            f"Idioma no soportado: '{lang_raw}'. Solo se admite Inglés y Español.",
            400,
            "UNSUPPORTED_LANGUAGE",
        )
    return LANGUAGE_MAP[cleaned]


def validate_text_translation_payload(data: Any) -> Tuple[str, str, str]:
    """
    Valida el cuerpo JSON para la traducción de texto.
    Retorna (texto, source_lang_code, target_lang_code).
    """
    if not isinstance(data, dict):
        raise ValidationError("El formato de la solicitud debe ser un objeto JSON válido.", 400, "INVALID_JSON")

    text = data.get("text")
    if text is None:
        text = data.get("texto", "")

    if not isinstance(text, str) or not text.strip():
        raise ValidationError("El texto a traducir no puede estar vacío.", 400, "EMPTY_TEXT")

    if len(text) > Config.MAX_TEXT_TRANSLATION_CHARS:
        raise ValidationError(
            f"El texto supera el límite permitido de {Config.MAX_TEXT_TRANSLATION_CHARS} caracteres.",
            400,
            "TEXT_TOO_LONG",
        )

    source_raw = data.get("source_lang") or data.get("idioma_origen") or "en"
    target_raw = data.get("target_lang") or data.get("idioma_destino") or "es"

    source_lang = normalize_language(source_raw)
    target_lang = normalize_language(target_raw)

    if source_lang == target_lang:
        raise ValidationError(
            "El idioma de origen y el de destino deben ser diferentes.",
            400,
            "SAME_LANGUAGE",
        )

    return text, source_lang, target_lang


def sanitize_filename_stem(filename: str) -> str:
    """Limpia el nombre base de un archivo para mostrar o descargar de forma segura."""
    if not filename:
        return "documento"
    base = os.path.basename(filename)
    stem, _ = os.path.splitext(base)
    safe_stem = re.sub(r"[^a-zA-Z0-9_\-\.áéíóúÁÉÍÓÚñÑ ]", "", stem).strip()
    safe_stem = re.sub(r"\s+", "-", safe_stem)
    return safe_stem[:80] if safe_stem else "documento"


def validate_pdf_file(file_path: Path, original_filename: str, file_size: int) -> Dict[str, Any]:
    """
    Valida exhaustivamente un archivo PDF recibido:
    1. Nombre y extensión .pdf
    2. Tamaño > 0 y <= 10 MB
    3. Cabecera mágica %PDF-
    4. Integridad estructural mediante PyMuPDF
    5. No protegido por contraseña
    6. Cantidad de páginas entre 1 y 20
    """
    if not original_filename or not original_filename.strip():
        raise ValidationError("No se seleccionó ningún archivo.", 400, "NO_FILE")

    _, ext = os.path.splitext(original_filename.lower().strip())
    if ext not in Config.ALLOWED_EXTENSIONS:
        raise ValidationError(
            "Formato de archivo no válido. Solo se permiten documentos en formato PDF (.pdf).",
            400,
            "INVALID_EXTENSION",
        )

    if file_size <= 0:
        raise ValidationError("El archivo enviado está vacío.", 400, "EMPTY_FILE")

    if file_size > Config.MAX_FILE_SIZE_BYTES:
        size_mb = round(file_size / (1024 * 1024), 2)
        raise ValidationError(
            f"El archivo es demasiado grande ({size_mb} MB). El tamaño máximo permitido es {Config.MAX_FILE_SIZE_MB} MB.",
            413,
            "FILE_TOO_LARGE",
        )

    # Verificar firma mágica %PDF- en los primeros bytes
    try:
        with open(file_path, "rb") as f:
            header = f.read(1024)
    except OSError:
        raise ValidationError("No se pudo leer el archivo enviado.", 400, "FILE_READ_ERROR")

    if b"%PDF-" not in header:
        raise ValidationError(
            "El archivo no es un documento PDF válido o está dañado.",
            400,
            "INVALID_PDF_HEADER",
        )

    # Abrir con PyMuPDF para verificar integridad y número de páginas
    try:
        doc = fitz.open(str(file_path))
    except Exception:
        raise ValidationError(
            "El archivo PDF está dañado o corrupto y no puede procesarse.",
            400,
            "CORRUPTED_PDF",
        )

    try:
        if doc.needs_pass or doc.is_encrypted:
            raise ValidationError(
                "El documento PDF está protegido con contraseña y no puede procesarse.",
                400,
                "ENCRYPTED_PDF",
            )

        if not doc.is_pdf:
            raise ValidationError(
                "El archivo proporcionado no tiene una estructura PDF válida.",
                400,
                "NOT_A_PDF",
            )

        page_count = doc.page_count
        if page_count <= 0:
            if getattr(doc, "is_repaired", False):
                raise ValidationError(
                    "El archivo PDF está dañado o corrupto y no puede procesarse.",
                    400,
                    "CORRUPTED_PDF",
                )
            raise ValidationError(
                "El documento PDF está vacío o dañado y no contiene páginas válidas.",
                400,
                "EMPTY_PDF_PAGES",
            )

        # Verificar que al menos la primera página pueda cargarse sin errores de estructura
        try:
            _ = doc.load_page(0)
        except Exception:
            raise ValidationError(
                "El archivo PDF está dañado o corrupto y no puede procesarse.",
                400,
                "CORRUPTED_PDF",
            )

        if page_count > Config.MAX_PDF_PAGES:
            raise ValidationError(
                f"El documento tiene {page_count} páginas y supera el máximo permitido de {Config.MAX_PDF_PAGES} páginas.",
                400,
                "TOO_MANY_PAGES",
            )

        return {
            "page_count": page_count,
            "file_size_bytes": file_size,
            "safe_stem": sanitize_filename_stem(original_filename),
        }
    finally:
        doc.close()
