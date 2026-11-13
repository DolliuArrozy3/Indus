import os
import re
import uuid
import threading
from io import BytesIO
from pathlib import Path
from flask import Blueprint, request, jsonify, send_file
import pymupdf as fitz  # PyMuPDF

from backend.config import Config
from backend.utils.validators import (
    validate_pdf_file,
    normalize_language,
    sanitize_filename_stem,
    ValidationError,
)
from backend.services.job_manager import (
    ensure_temp_dir,
    create_job_record,
    get_job,
    process_pdf_job,
    serialize_job_response,
)

pdf_bp = Blueprint("pdf_routes", __name__)

_JOB_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")


def _save_incoming_file_temporarily(file_storage) -> tuple[Path, str, int]:
    """
    Guarda el archivo subido en el directorio temporal seguro del servidor
    con un nombre generado por UUID, verificando su tamaño.
    """
    original_filename = file_storage.filename or ""
    if not original_filename.strip():
        raise ValidationError("No se seleccionó ningún archivo.", 400, "NO_FILE")

    temp_dir = ensure_temp_dir()
    temp_input_path = temp_dir / f"in_{uuid.uuid4().hex}.pdf"

    try:
        file_storage.save(str(temp_input_path))
        file_size = temp_input_path.stat().st_size
    except Exception:
        temp_input_path.unlink(missing_ok=True)
        raise ValidationError("No se pudo guardar temporalmente el archivo recibido.", 500, "FILE_SAVE_ERROR")

    return temp_input_path, original_filename, file_size


@pdf_bp.route("/api/translate/pdf/validate", methods=["POST"])
def validate_pdf_endpoint():
    """
    Valida rápidamente un archivo PDF seleccionado en el frontend y devuelve
    su cantidad real de páginas y tamaño en bytes.
    """
    files_list = request.files.getlist("file")
    if not files_list or len(files_list) == 0 or not files_list[0].filename:
        return (
            jsonify(
                {
                    "status": "error",
                    "error": "No se ha enviado ningún archivo PDF.",
                    "code": "NO_FILE",
                }
            ),
            400,
        )

    if len(files_list) > 1:
        return (
            jsonify(
                {
                    "status": "error",
                    "error": "Solo se permite procesar un documento por operación.",
                    "code": "MULTIPLE_FILES_NOT_ALLOWED",
                }
            ),
            400,
        )

    temp_path = None
    try:
        temp_path, original_filename, file_size = _save_incoming_file_temporarily(files_list[0])
        meta = validate_pdf_file(temp_path, original_filename, file_size)
        return (
            jsonify(
                {
                    "status": "ok",
                    "filename": os.path.basename(original_filename),
                    "safe_stem": meta["safe_stem"],
                    "file_size_bytes": meta["file_size_bytes"],
                    "page_count": meta["page_count"],
                }
            ),
            200,
        )
    except ValidationError as val_err:
        return (
            jsonify(
                {
                    "status": "error",
                    "error": val_err.message,
                    "code": val_err.code,
                }
            ),
            val_err.status_code,
        )
    except Exception:
        return (
            jsonify(
                {
                    "status": "error",
                    "error": "Error al validar el documento PDF.",
                    "code": "VALIDATION_INTERNAL_ERROR",
                }
            ),
            500,
        )
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)


@pdf_bp.route("/api/translate/pdf", methods=["POST"])
def translate_pdf_endpoint():
    """
    Recibe un archivo PDF, lo valida y ejecuta el proceso de extracción
    (directa / OCR / híbrida), traducción con OpenRouter y generación con ReportLab.
    Soporta ejecución asíncrona (async=true) o síncrona (por defecto).
    """
    files_list = request.files.getlist("file")
    if not files_list or len(files_list) == 0 or not files_list[0].filename:
        return (
            jsonify(
                {
                    "status": "error",
                    "error": "No se ha enviado ningún archivo PDF.",
                    "code": "NO_FILE",
                }
            ),
            400,
        )

    if len(files_list) > 1:
        return (
            jsonify(
                {
                    "status": "error",
                    "error": "Solo se permite procesar un documento por operación.",
                    "code": "MULTIPLE_FILES_NOT_ALLOWED",
                }
            ),
            400,
        )

    source_raw = request.form.get("source_lang", "en")
    target_raw = request.form.get("target_lang", "es")
    async_mode = (
        request.args.get("async", "").lower() in ("true", "1", "yes")
        or request.form.get("async", "").lower() in ("true", "1", "yes")
    )

    temp_input_path = None
    try:
        source_lang = normalize_language(source_raw)
        target_lang = normalize_language(target_raw)
        if source_lang == target_lang:
            raise ValidationError(
                "El idioma de origen y el de destino deben ser diferentes.",
                400,
                "SAME_LANGUAGE",
            )

        temp_input_path, original_filename, file_size = _save_incoming_file_temporarily(files_list[0])
        # Validar extensión, tamaño, firma PDF, integridad y límite de 20 páginas antes de encolar
        meta = validate_pdf_file(temp_input_path, original_filename, file_size)

        job = create_job_record(
            original_filename=os.path.basename(original_filename),
            safe_stem=meta["safe_stem"],
            input_path=temp_input_path,
            file_size_bytes=file_size,
            source_lang=source_lang,
            target_lang=target_lang,
        )
        job_id = job["job_id"]

        if async_mode:
            worker = threading.Thread(target=process_pdf_job, args=(job_id,), daemon=True)
            worker.start()
            current_job = get_job(job_id) or job
            return jsonify(serialize_job_response(current_job)), 202

        finished_job = process_pdf_job(job_id)
        http_status = finished_job.get("http_status", 200)
        return jsonify(serialize_job_response(finished_job)), http_status

    except ValidationError as val_err:
        if temp_input_path and temp_input_path.exists():
            temp_input_path.unlink(missing_ok=True)
        return (
            jsonify(
                {
                    "status": "error",
                    "error": val_err.message,
                    "code": val_err.code,
                }
            ),
            val_err.status_code,
        )
    except Exception:
        if temp_input_path and temp_input_path.exists():
            temp_input_path.unlink(missing_ok=True)
        return (
            jsonify(
                {
                    "status": "error",
                    "error": "Error interno al iniciar el procesamiento del archivo PDF.",
                    "code": "INTERNAL_SERVER_ERROR",
                }
            ),
            500,
        )


@pdf_bp.route("/api/translate/pdf/<job_id>", methods=["GET"])
def get_pdf_job_status(job_id: str):
    """Consulta el estado actual o el resultado final de la traducción de un PDF."""
    if not _JOB_ID_PATTERN.match(job_id or ""):
        return (
            jsonify(
                {
                    "status": "error",
                    "error": "Identificador de procesamiento inválido.",
                    "code": "INVALID_JOB_ID",
                }
            ),
            400,
        )

    job = get_job(job_id)
    if not job:
        return (
            jsonify(
                {
                    "status": "error",
                    "error": "No se encontró el documento solicitado o su tiempo de conservación ha expirado.",
                    "code": "JOB_NOT_FOUND",
                }
            ),
            404,
        )

    http_code = 200 if job["status"] != "error" else job.get("http_status", 500)
    return jsonify(serialize_job_response(job)), http_code


@pdf_bp.route("/api/translate/pdf/<job_id>/download", methods=["GET"])
def download_translated_pdf(job_id: str):
    """Descarga el archivo PDF traducido generado por ReportLab."""
    if not _JOB_ID_PATTERN.match(job_id or ""):
        return jsonify({"status": "error", "error": "Identificador inválido.", "code": "INVALID_JOB_ID"}), 400

    job = get_job(job_id)
    if not job or job.get("status") != "completed":
        return (
            jsonify(
                {
                    "status": "error",
                    "error": "El documento traducido no está disponible para descarga.",
                    "code": "DOCUMENT_NOT_READY",
                }
            ),
            404,
        )

    output_path = Path(job["output_path"])
    if not output_path.is_file():
        return (
            jsonify(
                {
                    "status": "error",
                    "error": "El archivo temporal ya no se encuentra en el servidor.",
                    "code": "FILE_EXPIRED",
                }
            ),
            404,
        )

    return send_file(
        str(output_path),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=job["output_filename"],
    )


@pdf_bp.route("/api/translate/pdf/<job_id>/view", methods=["GET"])
def view_translated_pdf(job_id: str):
    """Sirve el archivo PDF traducido en línea para visualización."""
    if not _JOB_ID_PATTERN.match(job_id or ""):
        return jsonify({"status": "error", "error": "Identificador inválido.", "code": "INVALID_JOB_ID"}), 400

    job = get_job(job_id)
    if not job or job.get("status") != "completed":
        return (
            jsonify(
                {
                    "status": "error",
                    "error": "El documento traducido no está disponible para visualización.",
                    "code": "DOCUMENT_NOT_READY",
                }
            ),
            404,
        )

    output_path = Path(job["output_path"])
    if not output_path.is_file():
        return (
            jsonify(
                {
                    "status": "error",
                    "error": "El archivo temporal ya no se encuentra en el servidor.",
                    "code": "FILE_EXPIRED",
                }
            ),
            404,
        )

    return send_file(
        str(output_path),
        mimetype="application/pdf",
        as_attachment=False,
        download_name=job["output_filename"],
    )


@pdf_bp.route("/api/translate/pdf/<job_id>/page/<int:page_num>", methods=["GET"])
def render_translated_pdf_page(job_id: str, page_num: int):
    """
    Renderiza una página específica del PDF traducido como imagen PNG de alta nitidez
    para el visor integrado del frontend.
    """
    if not _JOB_ID_PATTERN.match(job_id or ""):
        return jsonify({"status": "error", "error": "Identificador inválido.", "code": "INVALID_JOB_ID"}), 400

    job = get_job(job_id)
    if not job or job.get("status") != "completed":
        return jsonify({"status": "error", "error": "Documento no disponible.", "code": "DOCUMENT_NOT_READY"}), 404

    output_path = Path(job["output_path"])
    if not output_path.is_file():
        return jsonify({"status": "error", "error": "Archivo expirado.", "code": "FILE_EXPIRED"}), 404

    try:
        doc = fitz.open(str(output_path))
        try:
            if page_num < 1 or page_num > doc.page_count:
                return (
                    jsonify(
                        {
                            "status": "error",
                            "error": f"Número de página fuera de rango (1 a {doc.page_count}).",
                            "code": "PAGE_OUT_OF_RANGE",
                        }
                    ),
                    404,
                )
            page = doc.load_page(page_num - 1)
            pix = page.get_pixmap(dpi=160, alpha=False)
            png_bytes = pix.tobytes("png")
        finally:
            doc.close()

        return send_file(
            BytesIO(png_bytes),
            mimetype="image/png",
            as_attachment=False,
        )
    except Exception:
        return (
            jsonify(
                {
                    "status": "error",
                    "error": "No se pudo renderizar la página solicitada.",
                    "code": "PAGE_RENDER_ERROR",
                }
            ),
            500,
        )
