from flask import Blueprint, request, jsonify

from backend.utils.validators import (
    validate_text_translation_payload,
    ValidationError,
    LANGUAGE_NAMES,
)
from backend.services.translation_service import translate_text, TranslationError

text_bp = Blueprint("text_routes", __name__)


@text_bp.route("/api/translate", methods=["POST"])
def translate_text_endpoint():
    """
    Endpoint para traducir texto entre inglés y español.
    Recibe JSON: { "text": "...", "source_lang": "en", "target_lang": "es" }
    """
    if not request.is_json:
        return (
            jsonify(
                {
                    "status": "error",
                    "error": "La solicitud debe enviarse en formato JSON (Content-Type: application/json).",
                    "code": "INVALID_CONTENT_TYPE",
                }
            ),
            400,
        )

    data = request.get_json(silent=True)
    if data is None:
        return (
            jsonify(
                {
                    "status": "error",
                    "error": "El cuerpo JSON enviado no es válido.",
                    "code": "INVALID_JSON",
                }
            ),
            400,
        )

    try:
        text, source_lang, target_lang = validate_text_translation_payload(data)
        translated = translate_text(text, source_lang=source_lang, target_lang=target_lang)

        return (
            jsonify(
                {
                    "status": "ok",
                    "original_text": text,
                    "translated_text": translated,
                    "source_lang": source_lang,
                    "target_lang": target_lang,
                    "source_lang_name": LANGUAGE_NAMES.get(source_lang, "Inglés"),
                    "target_lang_name": LANGUAGE_NAMES.get(target_lang, "Español"),
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
    except TranslationError as trans_err:
        return (
            jsonify(
                {
                    "status": "error",
                    "error": trans_err.message,
                    "code": trans_err.code,
                }
            ),
            trans_err.status_code,
        )
    except Exception:
        return (
            jsonify(
                {
                    "status": "error",
                    "error": "Ocurrió un error interno al procesar la traducción.",
                    "code": "INTERNAL_SERVER_ERROR",
                }
            ),
            500,
        )
