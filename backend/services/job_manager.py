import os
import time
import uuid
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List
import pymupdf as fitz  # PyMuPDF

from backend.config import Config
from backend.utils.validators import (
    validate_pdf_file,
    ValidationError,
    LANGUAGE_NAMES,
)
from backend.services.pdf_extraction import extract_pdf_content, ExtractionError
from backend.services.ocr_service import OCRError
from backend.services.translation_service import (
    split_text_into_chunks,
    translate_single_chunk,
    TranslationError,
    check_openrouter_credentials,
)
from backend.services.pdf_generator import generate_translated_pdf, PDFGenerationError


# Almacenamiento en memoria de trabajos de traducción PDF (sin base de datos para el MVP)
_JOBS: Dict[str, Dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()


def ensure_temp_dir() -> Path:
    """Asegura que exista el directorio temporal privado del backend."""
    temp_dir = Config.TEMP_STORAGE_DIR
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir


def cleanup_expired_jobs() -> None:
    """
    Elimina archivos temporales y registros en memoria cuyo tiempo de vida
    (TEMP_FILE_TTL_SECONDS) haya expirado.
    """
    now = time.time()
    ttl = Config.TEMP_FILE_TTL_SECONDS
    expired_ids: List[str] = []

    with _JOBS_LOCK:
        for job_id, job in _JOBS.items():
            created_at = job.get("created_at", now)
            if now - created_at > ttl:
                expired_ids.append(job_id)

        for job_id in expired_ids:
            job = _JOBS.pop(job_id, None)
            if job:
                _safe_remove_file(job.get("input_path"))
                _safe_remove_file(job.get("output_path"))

    # Limpiar también archivos huérfanos en el directorio temporal
    temp_dir = Config.TEMP_STORAGE_DIR
    if temp_dir.exists():
        for file_path in temp_dir.glob("*"):
            try:
                if file_path.is_file() and (now - file_path.stat().st_mtime > ttl):
                    file_path.unlink(missing_ok=True)
            except OSError:
                pass


def _safe_remove_file(path_str: Optional[str]) -> None:
    """Elimina un archivo temporal de forma segura sin lanzar excepciones."""
    if not path_str:
        return
    try:
        Path(path_str).unlink(missing_ok=True)
    except OSError:
        pass


def create_job_record(
    original_filename: str,
    safe_stem: str,
    input_path: Path,
    file_size_bytes: int,
    source_lang: str = "en",
    target_lang: str = "es",
) -> Dict[str, Any]:
    """Crea un nuevo registro de trabajo con un identificador UUID seguro."""
    cleanup_expired_jobs()
    job_id = uuid.uuid4().hex
    output_filename = f"{safe_stem}-{target_lang}.pdf"
    output_path = ensure_temp_dir() / f"out_{job_id}.pdf"

    job_data = {
        "job_id": job_id,
        "status": "received",
        "step": "extraction",
        "status_message": "Archivo recibido. Validando documento...",
        "progress": None,
        "original_filename": original_filename,
        "output_filename": output_filename,
        "file_size_bytes": file_size_bytes,
        "source_lang": source_lang,
        "target_lang": target_lang,
        "source_lang_name": LANGUAGE_NAMES.get(source_lang, "Inglés"),
        "target_lang_name": LANGUAGE_NAMES.get(target_lang, "Español"),
        "input_path": str(input_path),
        "output_path": str(output_path),
        "source_pages_count": 0,
        "output_pages_count": 0,
        "document_type": None,
        "used_ocr": False,
        "translated_pages": [],
        "error": None,
        "error_code": None,
        "http_status": 200,
        "created_at": time.time(),
        "completed_at": None,
    }

    with _JOBS_LOCK:
        _JOBS[job_id] = job_data

    return job_data


def update_job(job_id: str, **updates) -> None:
    """Actualiza de forma segura el estado de un trabajo."""
    with _JOBS_LOCK:
        if job_id in _JOBS:
            _JOBS[job_id].update(updates)


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Recupera la información de un trabajo por su ID."""
    cleanup_expired_jobs()
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        return dict(job) if job else None


def serialize_job_response(job: Dict[str, Any]) -> Dict[str, Any]:
    """
    Serializa el estado de un trabajo para enviarlo al frontend sin exponer
    rutas internas del sistema de archivos.
    """
    job_id = job["job_id"]
    is_completed = job["status"] == "completed"
    return {
        "job_id": job_id,
        "status": job["status"],
        "step": job["step"],
        "status_message": job["status_message"],
        "progress": job["progress"],
        "original_filename": job["original_filename"],
        "output_filename": job["output_filename"],
        "file_size_bytes": job["file_size_bytes"],
        "source_lang": job["source_lang"],
        "target_lang": job["target_lang"],
        "source_lang_name": job["source_lang_name"],
        "target_lang_name": job["target_lang_name"],
        "source_pages_count": job["source_pages_count"],
        "output_pages_count": job["output_pages_count"],
        "document_type": job["document_type"],
        "used_ocr": job["used_ocr"],
        "error": job["error"],
        "error_code": job["error_code"],
        "download_url": f"/api/translate/pdf/{job_id}/download" if is_completed else None,
        "view_url": f"/api/translate/pdf/{job_id}/view" if is_completed else None,
        "pages_preview": [
            {
                "page_number": p["page_number"],
                "translated_text": p["translated_text"],
                "method": p.get("method", "direct"),
            }
            for p in job.get("translated_pages", [])
        ]
        if is_completed
        else [],
    }


def process_pdf_job(job_id: str) -> Dict[str, Any]:
    """
    Ejecuta el flujo completo de procesamiento de un PDF:
    1. Validación estructural del PDF.
    2. Extracción inteligente por página (PyMuPDF directo / Tesseract OCR / híbrido).
    3. Traducción por fragmentos mediante OpenRouter.
    4. Generación del nuevo PDF con ReportLab.
    5. Limpieza inmediata del archivo PDF de entrada.
    """
    job = get_job(job_id)
    if not job:
        raise ValidationError("El identificador del trabajo no existe.", 404, "JOB_NOT_FOUND")

    input_path = Path(job["input_path"])
    output_path = Path(job["output_path"])
    source_lang = job["source_lang"]
    target_lang = job["target_lang"]

    try:
        # 1. Validación del documento
        update_job(
            job_id,
            status="validating",
            step="extraction",
            status_message="Validando documento PDF...",
        )
        pdf_meta = validate_pdf_file(
            input_path,
            job["original_filename"],
            job["file_size_bytes"],
        )
        source_pages_count = pdf_meta["page_count"]
        update_job(job_id, source_pages_count=source_pages_count)

        # Verificar credenciales de OpenRouter antes de iniciar extracción pesada
        check_openrouter_credentials()

        # 2. Extracción de texto (seleccionable, escaneado o híbrido)
        def _extraction_status_cb(mode: str, page_num: int, total_pages: int):
            if mode == "ocr":
                update_job(
                    job_id,
                    status="ocr",
                    step="extraction",
                    status_message=f"Aplicando OCR en página {page_num} de {total_pages}...",
                )
            else:
                update_job(
                    job_id,
                    status="extracting",
                    step="extraction",
                    status_message=f"Extrayendo texto de página {page_num} de {total_pages}...",
                )

        extraction_result = extract_pdf_content(
            input_path,
            source_lang=source_lang,
            status_callback=_extraction_status_cb,
        )

        extracted_pages = extraction_result["pages"]
        doc_type = extraction_result["document_type"]
        used_ocr = extraction_result["used_ocr"]

        update_job(
            job_id,
            document_type=doc_type,
            used_ocr=used_ocr,
        )

        # 3. Preparar fragmentos por página para traducción
        page_chunks_map: List[Dict[str, Any]] = []
        total_chunks = 0
        for p in extracted_pages:
            p_text = (p.get("text") or "").strip()
            if p_text:
                chunks = split_text_into_chunks(p_text, Config.MAX_CHUNK_CHARS)
            else:
                chunks = []
            page_chunks_map.append(
                {
                    "page_number": p["page_number"],
                    "method": p["method"],
                    "chunks": chunks,
                }
            )
            total_chunks += len(chunks)

        if total_chunks == 0:
            raise ExtractionError(
                "No se encontró texto traducible en ninguna página del documento.",
                422,
                "NO_TRANSLATABLE_CONTENT",
            )

        # 4. Traducir cada fragmento en orden
        translated_pages: List[Dict[str, Any]] = []
        completed_chunks = 0

        update_job(
            job_id,
            status="translating",
            step="translation",
            status_message=f"Traduciendo contenido (0 de {total_chunks} fragmentos)...",
            progress=round((completed_chunks / total_chunks) * 100),
        )

        import requests

        with requests.Session() as session:
            for page_item in page_chunks_map:
                p_num = page_item["page_number"]
                p_chunks = page_item["chunks"]
                translated_page_parts: List[str] = []

                for chunk in p_chunks:
                    update_job(
                        job_id,
                        status="translating",
                        step="translation",
                        status_message=f"Traduciendo página {p_num} de {source_pages_count}...",
                        progress=round((completed_chunks / total_chunks) * 100),
                    )
                    translated_part = translate_single_chunk(
                        chunk,
                        source_lang=source_lang,
                        target_lang=target_lang,
                        session=session,
                    )
                    if not translated_part or not translated_part.strip():
                        raise TranslationError(
                            f"La traducción quedó incompleta en la página {p_num}. No se generó el documento final.",
                            502,
                            "INCOMPLETE_PAGE_TRANSLATION",
                        )
                    translated_page_parts.append(translated_part)
                    completed_chunks += 1
                    update_job(
                        job_id,
                        progress=round((completed_chunks / total_chunks) * 100),
                    )

                translated_pages.append(
                    {
                        "page_number": p_num,
                        "method": page_item["method"],
                        "translated_text": "\n\n".join(translated_page_parts),
                    }
                )

        # 5. Generar el PDF traducido con ReportLab
        update_job(
            job_id,
            status="generating",
            step="generation",
            status_message="Generando documento PDF traducido...",
            progress=100,
        )

        generate_translated_pdf(
            translated_pages=translated_pages,
            output_path=output_path,
            title=job["output_filename"],
        )

        # Verificar número de páginas del PDF generado con PyMuPDF
        output_pages_count = len(translated_pages)
        try:
            out_doc = fitz.open(str(output_path))
            output_pages_count = out_doc.page_count
            out_doc.close()
        except Exception:
            raise PDFGenerationError(
                "El PDF generado no pudo validarse correctamente.",
                500,
                "GENERATED_PDF_INVALID",
            )

        update_job(
            job_id,
            status="completed",
            step="completed",
            status_message="Proceso completado.",
            progress=100,
            output_pages_count=output_pages_count,
            translated_pages=translated_pages,
            completed_at=time.time(),
            http_status=200,
        )

    except (ValidationError, ExtractionError, OCRError, TranslationError, PDFGenerationError) as known_exc:
        _safe_remove_file(str(output_path))
        update_job(
            job_id,
            status="error",
            step="error",
            status_message=known_exc.message,
            error=known_exc.message,
            error_code=getattr(known_exc, "code", "PROCESSING_ERROR"),
            http_status=getattr(known_exc, "status_code", 500),
        )
    except Exception:
        _safe_remove_file(str(output_path))
        update_job(
            job_id,
            status="error",
            step="error",
            status_message="Ocurrió un error interno inesperado durante el procesamiento del PDF.",
            error="Ocurrió un error interno inesperado durante el procesamiento del PDF.",
            error_code="INTERNAL_ERROR",
            http_status=500,
        )
    finally:
        # Eliminar siempre el PDF original de entrada al finalizar el procesamiento
        _safe_remove_file(str(input_path))

    return get_job(job_id)
