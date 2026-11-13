import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = Path(__file__).resolve().parent

# Cargar variables de entorno desde la raíz del proyecto o carpeta backend
load_dotenv(BASE_DIR / ".env", override=False)
load_dotenv(BACKEND_DIR / ".env", override=False)


class Config:
    """Configuración centralizada del backend de Indus."""

    PROJECT_ROOT = BASE_DIR
    TEMP_STORAGE_DIR = BACKEND_DIR / "temp_storage"

    # Límites obligatorios del MVP
    MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "10"))
    MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
    MAX_PDF_PAGES = int(os.getenv("MAX_PDF_PAGES", "20"))
    ALLOWED_EXTENSIONS = {".pdf"}

    # Umbral para detección de páginas escaneadas / híbridas
    MIN_CHARS_FOR_DIRECT_EXTRACTION = 25

    # Tamaño máximo de fragmento (en caracteres) por petición a OpenRouter
    MAX_CHUNK_CHARS = 3200
    MAX_TEXT_TRANSLATION_CHARS = 15000

    # Tiempo de vida de archivos temporales (segundos)
    TEMP_FILE_TTL_SECONDS = int(os.getenv("TEMP_FILE_TTL_SECONDS", "1800"))

    # Configuración del servidor Flask
    FLASK_HOST = os.getenv("FLASK_HOST", "127.0.0.1")
    FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
    FLASK_DEBUG = os.getenv("FLASK_DEBUG", "True").lower() in ("true", "1", "yes")

    @staticmethod
    def get_openrouter_api_key() -> str:
        load_dotenv(BASE_DIR / ".env", override=False)
        return os.getenv("OPENROUTER_API_KEY", "").strip()

    @staticmethod
    def get_openrouter_model() -> str:
        load_dotenv(BASE_DIR / ".env", override=False)
        return os.getenv("OPENROUTER_MODEL", "").strip()

    @staticmethod
    def get_openrouter_url() -> str:
        load_dotenv(BASE_DIR / ".env", override=False)
        return os.getenv(
            "OPENROUTER_API_URL",
            "https://openrouter.ai/api/v1/chat/completions",
        ).strip()

    @staticmethod
    def get_openrouter_timeout() -> int:
        try:
            return int(os.getenv("OPENROUTER_TIMEOUT", "60"))
        except ValueError:
            return 60

    @staticmethod
    def get_tesseract_cmd() -> str:
        load_dotenv(BASE_DIR / ".env", override=False)
        return os.getenv("TESSERACT_CMD", "").strip()
