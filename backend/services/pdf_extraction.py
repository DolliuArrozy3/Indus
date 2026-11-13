import re
from pathlib import Path
from typing import Callable, Dict, List, Any, Optional
import pymupdf as fitz  # PyMuPDF
from PIL import Image

from backend.config import Config
from backend.services.ocr_service import extract_text_from_image, OCRError


class ExtractionError(Exception):
    """Excepción para errores durante la extracción de texto del PDF."""

    def __init__(self, message: str, status_code: int = 422, code: str = "EXTRACTION_ERROR"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


def _extract_selectable_text_from_page(page: fitz.Page) -> str:
    """
    Extrae el texto seleccionable de una página de PyMuPDF respetando el orden
    de lectura y los saltos de párrafo.
    """
    blocks = page.get_text("blocks", sort=True)
    paragraphs: List[str] = []

    for block in blocks:
        # block = (x0, y0, x1, y1, "lines_text", block_no, block_type)
        # block_type == 0 corresponde a texto
        if len(block) >= 7 and block[6] != 0:
            continue
        raw_text = block[4] if len(block) >= 5 else ""
        if not raw_text or not raw_text.strip():
            continue

        # Limpiar espacios redundantes conservando saltos de línea significativos
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        if lines:
            paragraphs.append("\n".join(lines))

    return "\n\n".join(paragraphs).strip()


def _render_page_to_pil_image(page: fitz.Page, dpi: int = 200) -> Image.Image:
    """Convierte una página de PyMuPDF a un objeto PIL.Image para aplicar OCR."""
    pix = page.get_pixmap(dpi=dpi, alpha=False)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    return img


def extract_pdf_content(
    pdf_path: Path,
    source_lang: str = "en",
    status_callback: Optional[Callable[[str, int, int], None]] = None,
) -> Dict[str, Any]:
    """
    Extrae el contenido página por página de un archivo PDF soportando:
    - PDFs con texto seleccionable (PyMuPDF directo)
    - PDFs escaneados (Pillow + Tesseract OCR)
    - PDFs híbridos (combinación página por página de texto directo y OCR)

    Retorna un diccionario con:
    - 'pages': lista de dicts {'page_number', 'text', 'method'}
    - 'total_pages': int
    - 'document_type': 'selectable' | 'scanned' | 'hybrid'
    - 'used_ocr': bool
    """
    ocr_lang = "eng" if source_lang == "en" else "spa"

    try:
        doc = fitz.open(str(pdf_path))
    except Exception:
        raise ExtractionError(
            "No se pudo abrir el documento PDF para extraer su texto.",
            400,
            "PDF_OPEN_ERROR",
        )

    pages_result: List[Dict[str, Any]] = []
    used_direct = False
    used_ocr = False
    last_ocr_error: Optional[OCRError] = None

    try:
        total_pages = doc.page_count
        for idx in range(total_pages):
            page_num = idx + 1
            page = doc.load_page(idx)

            if status_callback:
                status_callback("extracting", page_num, total_pages)

            direct_text = _extract_selectable_text_from_page(page)
            non_ws_chars = len(re.sub(r"\s+", "", direct_text))
            has_images = len(page.get_images(full=False)) > 0

            # Determinar si la página requiere OCR:
            # 1. No tiene suficiente texto seleccionable (< umbral mínimo), o
            # 2. Tiene un texto mínimo (< 80 caracteres, ej. pie de página) pero contiene imágenes grandes escaneadas
            needs_ocr = (non_ws_chars < Config.MIN_CHARS_FOR_DIRECT_EXTRACTION) or (
                has_images and non_ws_chars < 60
            )

            if not needs_ocr:
                used_direct = True
                pages_result.append(
                    {
                        "page_number": page_num,
                        "text": direct_text,
                        "method": "direct",
                    }
                )
            else:
                if status_callback:
                    status_callback("ocr", page_num, total_pages)

                pil_img = _render_page_to_pil_image(page, dpi=200)
                try:
                    ocr_text = extract_text_from_image(pil_img, lang=ocr_lang)
                    used_ocr = True
                except OCRError as ocr_exc:
                    last_ocr_error = ocr_exc
                    ocr_text = ""

                # Si había algo de texto directo y también OCR, combinar o priorizar el más completo
                ocr_non_ws = len(re.sub(r"\s+", "", ocr_text))
                if ocr_non_ws >= non_ws_chars and ocr_non_ws > 0:
                    final_page_text = ocr_text
                    page_method = "ocr" if non_ws_chars == 0 else "hybrid"
                elif non_ws_chars > 0:
                    final_page_text = direct_text
                    page_method = "direct"
                    used_direct = True
                else:
                    final_page_text = ""
                    page_method = "ocr"

                pages_result.append(
                    {
                        "page_number": page_num,
                        "text": final_page_text,
                        "method": page_method,
                    }
                )
    finally:
        doc.close()

    total_extracted_chars = sum(len(re.sub(r"\s+", "", p["text"])) for p in pages_result)
    if total_extracted_chars == 0:
        if last_ocr_error is not None:
            raise last_ocr_error
        raise ExtractionError(
            "No se pudo extraer texto reconocible del documento PDF. El archivo parece estar en blanco o contener únicamente gráficos sin texto.",
            422,
            "NO_EXTRACTABLE_TEXT",
        )

    if used_direct and used_ocr:
        doc_type = "hybrid"
    elif used_ocr:
        doc_type = "scanned"
    else:
        doc_type = "selectable"

    return {
        "pages": pages_result,
        "total_pages": len(pages_result),
        "document_type": doc_type,
        "used_ocr": used_ocr,
    }
