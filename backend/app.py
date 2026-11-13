import sys
from pathlib import Path
from flask import Flask, jsonify, request, Response, send_from_directory, abort
from flask_cors import CORS
from werkzeug.exceptions import RequestEntityTooLarge

# Permitir ejecución tanto con 'python backend/app.py' como con 'python -m backend.app'
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import Config
from backend.routes.text_routes import text_bp
from backend.routes.pdf_routes import pdf_bp
from backend.services.ocr_service import is_tesseract_available, resolve_tesseract_executable


FRONTEND_HTML_FILES = {
    "index.html",
    "traductor-texto.html",
    "traductor-archivos.html",
}

FRONTEND_STATIC_FILES = {
    "estilo.css",
    "estilo-texto.css",
    "estilo-archivos.css",
    "javascript.js",
}


def _serve_html_with_script(filename: str) -> Response:
    """
    Lee el archivo HTML original desde el disco sin modificarlo y le inyecta
    en memoria la referencia a javascript.js antes de </body> (Opción 1).
    """
    file_path = Config.PROJECT_ROOT / filename
    if not file_path.is_file():
        abort(404)

    html_content = file_path.read_text(encoding="utf-8")
    if "javascript.js" not in html_content:
        script_tag = '  <script src="javascript.js"></script>\n</body>'
        if "</body>" in html_content:
            html_content = html_content.replace("</body>", script_tag, 1)
        else:
            html_content += '\n<script src="javascript.js"></script>'

    return Response(html_content, mimetype="text/html; charset=utf-8")


def create_app() -> Flask:
    """Crea y configura la aplicación Flask de Indus."""
    app = Flask(__name__, static_folder=None)

    # Tope de seguridad HTTP (la validación exacta de 10 MB se realiza en validators.py
    # para devolver siempre una respuesta JSON controlada sin cortar el socket en Windows)
    app.config["MAX_CONTENT_LENGTH"] = 30 * 1024 * 1024

    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Registrar blueprints de la API
    app.register_blueprint(text_bp)
    app.register_blueprint(pdf_bp)

    @app.route("/api/health", methods=["GET"])
    def health_check():
        """Endpoint de diagnóstico del estado del servidor (sin exponer credenciales)."""
        api_key = Config.get_openrouter_api_key()
        model = Config.get_openrouter_model()
        has_valid_key = bool(api_key and api_key.lower() not in ("tu_api_key", "tu_api_key_aqui"))
        has_valid_model = bool(model and model.lower() not in ("modelo_seleccionado", "tu_modelo"))

        return jsonify(
            {
                "status": "ok",
                "service": "Indus Backend",
                "openrouter_configured": has_valid_key and has_valid_model,
                "openrouter_model": model if has_valid_model else None,
                "tesseract_available": is_tesseract_available(),
                "tesseract_path": resolve_tesseract_executable(),
                "limits": {
                    "max_file_size_mb": Config.MAX_FILE_SIZE_MB,
                    "max_pdf_pages": Config.MAX_PDF_PAGES,
                },
            }
        )

    # Rutas del frontend (manteniendo los archivos HTML y CSS intactos en disco)
    @app.route("/", methods=["GET"])
    def index_root():
        return _serve_html_with_script("index.html")

    @app.route("/<path:filename>", methods=["GET"])
    def serve_frontend(filename: str):
        # Bloquear cualquier intento de acceso a directorios internos o archivos ocultos
        normalized = filename.replace("\\", "/").lstrip("/")
        if (
            ".." in normalized
            or normalized.startswith(".")
            or normalized.startswith("backend")
            or normalized.startswith("temp_storage")
        ):
            abort(404)

        if normalized in FRONTEND_HTML_FILES:
            return _serve_html_with_script(normalized)

        if normalized in FRONTEND_STATIC_FILES:
            return send_from_directory(str(Config.PROJECT_ROOT), normalized)

        if normalized.startswith("Archivos/"):
            rel_asset = normalized[len("Archivos/") :]
            if ".." in rel_asset or "/" in rel_asset:
                abort(404)
            archivos_dir = Config.PROJECT_ROOT / "Archivos"
            return send_from_directory(str(archivos_dir), rel_asset)

        abort(404)

    # Manejadores de errores HTTP
    @app.errorhandler(RequestEntityTooLarge)
    @app.errorhandler(413)
    def handle_file_too_large(_err):
        return (
            jsonify(
                {
                    "status": "error",
                    "error": f"El archivo supera el tamaño máximo permitido de {Config.MAX_FILE_SIZE_MB} MB.",
                    "code": "FILE_TOO_LARGE",
                }
            ),
            413,
        )

    @app.errorhandler(404)
    def handle_not_found(_err):
        if request.path.startswith("/api/"):
            return (
                jsonify(
                    {
                        "status": "error",
                        "error": "El recurso o endpoint solicitado no existe.",
                        "code": "NOT_FOUND",
                    }
                ),
                404,
            )
        return Response("Recurso no encontrado (404)", status=404, mimetype="text/plain; charset=utf-8")

    @app.errorhandler(405)
    def handle_method_not_allowed(_err):
        return (
            jsonify(
                {
                    "status": "error",
                    "error": "Método HTTP no permitido para este endpoint.",
                    "code": "METHOD_NOT_ALLOWED",
                }
            ),
            405,
        )

    @app.errorhandler(500)
    def handle_internal_error(_err):
        return (
            jsonify(
                {
                    "status": "error",
                    "error": "Error interno del servidor.",
                    "code": "INTERNAL_SERVER_ERROR",
                }
            ),
            500,
        )

    return app


app = create_app()

if __name__ == "__main__":
    app.run(
        host=Config.FLASK_HOST,
        port=Config.FLASK_PORT,
        debug=Config.FLASK_DEBUG,
    )
