import os
import shutil
from pathlib import Path
from typing import Optional
from PIL import Image, ImageOps
import pytesseract

from backend.config import Config


class OCRError(Exception):
    """Excepción para errores durante el reconocimiento óptico de caracteres (OCR)."""

    def __init__(self, message: str, status_code: int = 500, code: str = "OCR_ERROR"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


COMMON_WINDOWS_TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Tesseract-OCR\tesseract.exe"),
    os.path.expandvars(r"%USERPROFILE%\scoop\apps\tesseract\current\tesseract.exe"),
]


def resolve_tesseract_executable() -> Optional[str]:
    """
    Localiza el ejecutable de Tesseract OCR verificando:
    1. La variable de entorno TESSERACT_CMD en .env
    2. El PATH del sistema
    3. Las rutas estándar de instalación en Windows
    """
    env_cmd = Config.get_tesseract_cmd()
    if env_cmd:
        if Path(env_cmd).is_file():
            return str(Path(env_cmd))
        found_env = shutil.which(env_cmd)
        if found_env:
            return found_env

    which_cmd = shutil.which("tesseract")
    if which_cmd:
        return which_cmd

    for candidate in COMMON_WINDOWS_TESSERACT_PATHS:
        if candidate and Path(candidate).is_file():
            return candidate

    return None


def is_tesseract_available() -> bool:
    """Comprueba si Tesseract OCR está disponible y es ejecutable."""
    cmd = resolve_tesseract_executable()
    if not cmd:
        return False
    pytesseract.pytesseract.tesseract_cmd = cmd
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def preprocess_image_for_ocr(image: Image.Image) -> Image.Image:
    """
    Procesa la imagen con Pillow para mejorar la precisión del OCR:
    conversión a escala de grises y ajuste automático de contraste.
    """
    gray = image.convert("L")
    enhanced = ImageOps.autocontrast(gray, cutoff=1)
    return enhanced


def extract_text_from_image(image: Image.Image, lang: str = "eng") -> str:
    """
    Aplica Tesseract OCR sobre una imagen PIL y devuelve el texto reconocido.
    Lanza OCRError si Tesseract no está instalado o falla el procesamiento.
    """
    cmd = resolve_tesseract_executable()
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd

    processed_image = preprocess_image_for_ocr(image)

    try:
        text = pytesseract.image_to_string(processed_image, lang=lang)
    except pytesseract.TesseractNotFoundError:
        raise OCRError(
            "Error al realizar OCR: No se encontró Tesseract OCR en el sistema. "
            "Instala Tesseract OCR o configura la ruta TESSERACT_CMD en el archivo .env.",
            503,
            "TESSERACT_NOT_FOUND",
        )
    except pytesseract.TesseractError as exc:
        # Si falla por paquete de idioma específico, intentar con el idioma por defecto de Tesseract
        try:
            text = pytesseract.image_to_string(processed_image)
        except Exception:
            raise OCRError(
                f"Error al realizar OCR sobre la página escaneada ({str(exc)[:120]}).",
                500,
                "TESSERACT_EXECUTION_ERROR",
            )
    except Exception as exc:
        raise OCRError(
            f"No se pudo completar el reconocimiento óptico de caracteres (OCR): {str(exc)[:120]}",
            500,
            "OCR_FAILED",
        )

    return (text or "").strip()
