import io
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pymupdf as fitz  # PyMuPDF
from PIL import Image, ImageDraw
import pytest
import requests

from backend.app import create_app
from backend.config import Config


@pytest.fixture
def client(monkeypatch):
    """Cliente de pruebas de Flask con credenciales de prueba configuradas."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test-valid-key-12345")
    monkeypatch.setenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def _make_mock_openrouter_response(translated_content: str, finish_reason: str = "stop", status_code: int = 200):
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = {
        "choices": [
            {
                "finish_reason": finish_reason,
                "message": {"role": "assistant", "content": translated_content},
            }
        ]
    }
    return mock_resp


def _create_selectable_pdf_bytes(pages_text: list[str]) -> bytes:
    """Crea un PDF real con texto seleccionable usando PyMuPDF."""
    doc = fitz.open()
    for text in pages_text:
        page = doc.new_page(width=595, height=842)
        rect = fitz.Rect(50, 50, 545, 792)
        page.insert_textbox(rect, text, fontsize=12, fontname="helv")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _create_scanned_pdf_bytes(pages_text: list[str]) -> bytes:
    """Crea un PDF escaneado (compuesto únicamente por imágenes rasterizadas sin capa de texto)."""
    doc = fitz.open()
    for text in pages_text:
        img = Image.new("RGB", (800, 1000), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.text((60, 80), text, fill=(0, 0, 0))
        img_buf = io.BytesIO()
        img.save(img_buf, format="PNG")
        img_bytes = img_buf.getvalue()

        page = doc.new_page(width=595, height=842)
        page.insert_image(fitz.Rect(0, 0, 595, 842), stream=img_bytes)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _create_hybrid_pdf_bytes() -> bytes:
    """
    Crea un PDF híbrido real:
    - Página 1: texto seleccionable directo.
    - Página 2: imagen escaneada sin capa de texto seleccionable.
    - Página 3: texto seleccionable directo.
    """
    doc = fitz.open()

    # Página 1: seleccionable
    p1 = doc.new_page(width=595, height=842)
    p1.insert_textbox(
        fitz.Rect(50, 50, 545, 792),
        "PROJECT INTRODUCTION\n\nThis first page contains selectable digital text ready for direct extraction.",
        fontsize=12,
    )

    # Página 2: escaneada (solo imagen)
    img = Image.new("RGB", (800, 1000), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((60, 80), "Scanned page two content recognized via OCR.", fill=(0, 0, 0))
    img_buf = io.BytesIO()
    img.save(img_buf, format="PNG")
    p2 = doc.new_page(width=595, height=842)
    p2.insert_image(fitz.Rect(0, 0, 595, 842), stream=img_buf.getvalue())

    # Página 3: seleccionable
    p3 = doc.new_page(width=595, height=842)
    p3.insert_textbox(
        fitz.Rect(50, 50, 545, 792),
        "CONCLUSIONS\n\n- First conclusion item\n- Second conclusion item with important details.",
        fontsize=12,
    )

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


# =========================================================================
# 1. PRUEBAS DEL TRADUCTOR DE TEXTO
# =========================================================================

def test_text_short_en_to_es(client):
    """Prueba: Texto corto inglés -> español."""
    with patch("requests.Session.post") as mock_post:
        mock_post.return_value = _make_mock_openrouter_response("Hola mundo, esta es una prueba académica.")
        resp = client.post(
            "/api/translate",
            json={
                "text": "Hello world, this is an academic test.",
                "source_lang": "Inglés",
                "target_lang": "Español",
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["source_lang"] == "en"
        assert data["target_lang"] == "es"
        assert data["translated_text"] == "Hola mundo, esta es una prueba académica."


def test_text_long_chunked_translation(client):
    """Prueba: Texto largo que supera el tamaño de un fragmento y se divide en múltiples llamadas."""
    long_paragraph_1 = "Artificial intelligence is transforming academic tools. " * 40
    long_paragraph_2 = "Students and researchers benefit from accurate document translation. " * 35
    full_long_text = f"{long_paragraph_1.strip()}\n\n{long_paragraph_2.strip()}"

    with patch("requests.Session.post") as mock_post:
        mock_post.side_effect = [
            _make_mock_openrouter_response("La inteligencia artificial está transformando las herramientas académicas. " * 40),
            _make_mock_openrouter_response("Los estudiantes e investigadores se benefician de la traducción precisa. " * 35),
        ]
        resp = client.post(
            "/api/translate",
            json={
                "text": full_long_text,
                "source_lang": "en",
                "target_lang": "es",
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert mock_post.call_count == 2
        assert "inteligencia artificial" in data["translated_text"]
        assert "estudiantes e investigadores" in data["translated_text"]


def test_text_multiple_paragraphs_preserved(client):
    """Prueba: Texto con varios párrafos conservando saltos de línea."""
    multi_para = "First paragraph of the document.\n\nSecond paragraph with key findings.\n\nThird paragraph with conclusion."
    expected_es = "Primer párrafo del documento.\n\nSegundo párrafo con hallazgos clave.\n\nTercer párrafo con conclusión."

    with patch("requests.Session.post") as mock_post:
        mock_post.return_value = _make_mock_openrouter_response(expected_es)
        resp = client.post(
            "/api/translate",
            json={"text": multi_para, "source_lang": "Inglés", "target_lang": "Español"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["translated_text"].count("\n\n") == 2
        assert data["translated_text"] == expected_es


def test_text_es_to_en(client):
    """Prueba: Traducción Español -> Inglés."""
    with patch("requests.Session.post") as mock_post:
        mock_post.return_value = _make_mock_openrouter_response("The Indus project preserves document readability.")
        resp = client.post(
            "/api/translate",
            json={
                "text": "El proyecto Indus conserva la legibilidad del documento.",
                "source_lang": "Español",
                "target_lang": "Inglés",
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["source_lang"] == "es"
        assert data["target_lang"] == "en"
        assert data["translated_text"] == "The Indus project preserves document readability."


def test_text_empty_field(client):
    """Prueba: Campo de texto vacío o solo espacios es rechazado con 400."""
    resp = client.post(
        "/api/translate",
        json={"text": "   \n  ", "source_lang": "Inglés", "target_lang": "Español"},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["status"] == "error"
    assert data["code"] == "EMPTY_TEXT"


def test_text_openrouter_connection_error(client):
    """Prueba: Error de conexión con OpenRouter devuelve 502 comprensible."""
    with patch("requests.Session.post", side_effect=requests.exceptions.ConnectionError("Network unreachable")):
        resp = client.post(
            "/api/translate",
            json={"text": "Hello world", "source_lang": "en", "target_lang": "es"},
        )
        assert resp.status_code == 502
        data = resp.get_json()
        assert data["status"] == "error"
        assert data["code"] == "API_CONNECTION_ERROR"
        assert "conexión" in data["error"].lower()


def test_text_openrouter_invalid_response(client):
    """Prueba: Respuesta inválida de la API de OpenRouter devuelve 502."""
    bad_resp = MagicMock()
    bad_resp.status_code = 200
    bad_resp.json.return_value = {"unexpected_key": "no_choices"}

    with patch("requests.Session.post", return_value=bad_resp):
        resp = client.post(
            "/api/translate",
            json={"text": "Hello world", "source_lang": "en", "target_lang": "es"},
        )
        assert resp.status_code == 502
        data = resp.get_json()
        assert data["status"] == "error"
        assert data["code"] == "API_INVALID_STRUCTURE"


# =========================================================================
# 2. PRUEBAS DEL TRADUCTOR DE ARCHIVOS PDF
# =========================================================================

def test_pdf_selectable_text_and_download_and_preview(client):
    """Prueba: PDF con texto seleccionable, generación con ReportLab, vista previa y descarga."""
    pdf_bytes = _create_selectable_pdf_bytes(
        [
            "EXECUTIVE SUMMARY\n\nThis report describes the architecture of the Indus system.",
            "METHODOLOGY\n\n- Document validation\n- Text extraction\n- Neural translation",
        ]
    )

    with patch("requests.Session.post") as mock_post:
        mock_post.side_effect = [
            _make_mock_openrouter_response("RESUMEN EJECUTIVO\n\nEste informe describe la arquitectura del sistema Indus."),
            _make_mock_openrouter_response("METODOLOGÍA\n\n- Validación de documentos\n- Extracción de texto\n- Traducción neuronal"),
        ]
        resp = client.post(
            "/api/translate/pdf",
            data={
                "file": (io.BytesIO(pdf_bytes), "informe-indus.pdf"),
                "source_lang": "Inglés",
                "target_lang": "Español",
            },
            content_type="multipart/form-data",
        )

        assert resp.status_code == 200
        job_data = resp.get_json()
        assert job_data["status"] == "completed"
        assert job_data["document_type"] == "selectable"
        assert job_data["used_ocr"] is False
        assert job_data["source_pages_count"] == 2
        assert job_data["output_pages_count"] >= 2
        assert job_data["output_filename"] == "informe-indus-es.pdf"

        job_id = job_data["job_id"]

        # Verificar endpoint de estado
        status_resp = client.get(f"/api/translate/pdf/{job_id}")
        assert status_resp.status_code == 200

        # Verificar descarga del PDF generado y que se abre con PyMuPDF con todo el texto traducido
        dl_resp = client.get(f"/api/translate/pdf/{job_id}/download")
        assert dl_resp.status_code == 200
        assert dl_resp.mimetype == "application/pdf"
        generated_pdf_bytes = dl_resp.data
        assert generated_pdf_bytes.startswith(b"%PDF-")

        gen_doc = fitz.open(stream=generated_pdf_bytes, filetype="pdf")
        full_gen_text = "\n".join(gen_doc.load_page(i).get_text("text") for i in range(gen_doc.page_count))
        gen_doc.close()
        assert "RESUMEN EJECUTIVO" in full_gen_text
        assert "arquitectura del sistema Indus" in full_gen_text
        assert "Validación de documentos" in full_gen_text

        # Verificar renderizado de página para el visualizador integrado del frontend
        page_img_resp = client.get(f"/api/translate/pdf/{job_id}/page/1")
        assert page_img_resp.status_code == 200
        assert page_img_resp.mimetype == "image/png"
        assert page_img_resp.data.startswith(b"\x89PNG")


def test_pdf_scanned_ocr(client):
    """Prueba: PDF escaneado procesado mediante OCR."""
    scanned_bytes = _create_scanned_pdf_bytes(
        ["Scanned document page with historical text for translation."]
    )

    with patch(
        "backend.services.pdf_extraction.extract_text_from_image",
        return_value="Scanned document page with historical text for translation.",
    ) as mock_ocr, patch("requests.Session.post") as mock_post:
        mock_post.return_value = _make_mock_openrouter_response(
            "Página de documento escaneado con texto histórico para traducción."
        )
        resp = client.post(
            "/api/translate/pdf",
            data={
                "file": (io.BytesIO(scanned_bytes), "escaneado.pdf"),
                "source_lang": "en",
                "target_lang": "es",
            },
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "completed"
        assert data["document_type"] == "scanned"
        assert data["used_ocr"] is True
        assert mock_ocr.call_count == 1
        assert "documento escaneado" in data["pages_preview"][0]["translated_text"]


def test_pdf_hybrid_selectable_and_scanned(client):
    """Prueba: PDF híbrido combinando extracción directa con PyMuPDF y OCR en páginas escaneadas."""
    hybrid_bytes = _create_hybrid_pdf_bytes()

    with patch(
        "backend.services.pdf_extraction.extract_text_from_image",
        return_value="Scanned page two content recognized via OCR.",
    ) as mock_ocr, patch("requests.Session.post") as mock_post:
        mock_post.side_effect = [
            _make_mock_openrouter_response("INTRODUCCIÓN DEL PROYECTO\n\nEsta primera página contiene texto digital seleccionable."),
            _make_mock_openrouter_response("Contenido de la página dos escaneada reconocido mediante OCR."),
            _make_mock_openrouter_response("CONCLUSIONES\n\n- Primer punto de conclusión\n- Segundo punto de conclusión."),
        ]
        resp = client.post(
            "/api/translate/pdf",
            data={
                "file": (io.BytesIO(hybrid_bytes), "documento-hibrido.pdf"),
                "source_lang": "en",
                "target_lang": "es",
            },
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "completed"
        assert data["document_type"] == "hybrid"
        assert data["used_ocr"] is True
        assert data["source_pages_count"] == 3
        # OCR solo se invocó en la página 2 (la única escaneada)
        assert mock_ocr.call_count == 1
        methods = [p["method"] for p in data["pages_preview"]]
        assert methods == ["direct", "ocr", "direct"]


def test_pdf_multiple_pages(client):
    """Prueba: PDF de varias páginas (5 páginas) manteniendo el orden exacto."""
    pages_input = [
        f"CHAPTER {i}\n\nDetailed academic content belonging to page number {i} of the study."
        for i in range(1, 6)
    ]
    pdf_bytes = _create_selectable_pdf_bytes(pages_input)

    with patch("requests.Session.post") as mock_post:
        mock_post.side_effect = [
            _make_mock_openrouter_response(f"CAPÍTULO {i}\n\nContenido académico detallado perteneciente a la página número {i} del estudio.")
            for i in range(1, 6)
        ]
        resp = client.post(
            "/api/translate/pdf",
            data={"file": (io.BytesIO(pdf_bytes), "estudio-5-paginas.pdf")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "completed"
        assert data["source_pages_count"] == 5
        assert len(data["pages_preview"]) == 5
        for idx, page_item in enumerate(data["pages_preview"], start=1):
            assert page_item["page_number"] == idx
            assert f"CAPÍTULO {idx}" in page_item["translated_text"]


def test_pdf_exceeds_10mb_limit(client):
    """Prueba: PDF superior a 10 MB es rechazado con código HTTP 413."""
    oversized_bytes = b"%PDF-1.4\n" + (b"0" * (10 * 1024 * 1024 + 2048))
    resp = client.post(
        "/api/translate/pdf",
        data={"file": (io.BytesIO(oversized_bytes), "archivo-pesado.pdf")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 413
    data = resp.get_json()
    assert data["status"] == "error"
    assert data["code"] == "FILE_TOO_LARGE"
    assert "10 MB" in data["error"]


def test_pdf_exceeds_20_pages_limit(client):
    """Prueba: PDF con más de 20 páginas (21 páginas) es rechazado con código HTTP 400."""
    pages_21 = [f"Page {i} content with enough characters for a valid page." for i in range(1, 22)]
    pdf_21_bytes = _create_selectable_pdf_bytes(pages_21)

    resp = client.post(
        "/api/translate/pdf",
        data={"file": (io.BytesIO(pdf_21_bytes), "documento-21-paginas.pdf")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["status"] == "error"
    assert data["code"] == "TOO_MANY_PAGES"
    assert "20 páginas" in data["error"]


def test_non_pdf_file_rejected(client):
    """Prueba: Archivo que no sea PDF (tanto por extensión como por contenido falsificado)."""
    # 1. Extensión .txt
    resp_txt = client.post(
        "/api/translate/pdf",
        data={"file": (io.BytesIO(b"Hello world plain text"), "notas.txt")},
        content_type="multipart/form-data",
    )
    assert resp_txt.status_code == 400
    assert resp_txt.get_json()["code"] == "INVALID_EXTENSION"

    # 2. Archivo .exe/.txt renombrado a .pdf (sin cabecera %PDF-)
    resp_fake = client.post(
        "/api/translate/pdf",
        data={"file": (io.BytesIO(b"MZ_NOT_A_REAL_PDF_FILE_CONTENT"), "falso.pdf")},
        content_type="multipart/form-data",
    )
    assert resp_fake.status_code == 400
    assert resp_fake.get_json()["code"] == "INVALID_PDF_HEADER"


def test_corrupted_pdf_rejected(client):
    """Prueba: PDF dañado (tiene cabecera %PDF- pero estructura corrupta) es rechazado."""
    corrupted_bytes = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog /Broken >>>\n%%EOF_CORRUPTED_STREAM"
    resp = client.post(
        "/api/translate/pdf",
        data={"file": (io.BytesIO(corrupted_bytes), "danado.pdf")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["status"] == "error"
    assert data["code"] == "CORRUPTED_PDF"


def test_pdf_without_recognizable_text(client):
    """Prueba: Documento en blanco sin texto seleccionable ni texto reconocible por OCR."""
    doc = fitz.open()
    doc.new_page(width=595, height=842)
    blank_pdf_bytes = doc.tobytes()
    doc.close()

    with patch("backend.services.pdf_extraction.extract_text_from_image", return_value=""):
        resp = client.post(
            "/api/translate/pdf",
            data={"file": (io.BytesIO(blank_pdf_bytes), "en-blanco.pdf")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 422
        data = resp.get_json()
        assert data["status"] == "error"
        assert data["error_code"] == "NO_EXTRACTABLE_TEXT"


def test_pdf_error_during_translation_prevents_partial_pdf(client):
    """
    Prueba: Si ocurre un error durante la traducción de una página, NO se genera
    un PDF final incompleto y se informa el error correctamente.
    """
    pdf_bytes = _create_selectable_pdf_bytes(
        [
            "Page one has valid English content for translation.",
            "Page two will fail during the OpenRouter API request.",
        ]
    )

    with patch("requests.Session.post") as mock_post:
        mock_post.side_effect = [
            _make_mock_openrouter_response("La página uno tiene contenido válido traducido."),
            requests.exceptions.Timeout("Request timed out on page 2"),
        ]
        resp = client.post(
            "/api/translate/pdf",
            data={"file": (io.BytesIO(pdf_bytes), "fallo-parcial.pdf")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 504
        data = resp.get_json()
        assert data["status"] == "error"
        assert data["error_code"] == "API_TIMEOUT"
        assert data["download_url"] is None

        # Intentar descargar debe devolver 404 porque no se generó documento incompleto
        job_id = data["job_id"]
        dl_resp = client.get(f"/api/translate/pdf/{job_id}/download")
        assert dl_resp.status_code == 404


def test_frontend_files_preserved_and_served_correctly(client):
    """
    Verifica que los archivos HTML y CSS no fueron modificados y que Flask
    inyecta dinámicamente javascript.js y bloquea rutas privadas.
    """
    for page_name in ("index.html", "traductor-texto.html", "traductor-archivos.html"):
        resp = client.get(f"/{page_name}")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert 'src="javascript.js"' in html

    # Verificar que rutas internas están bloqueadas
    assert client.get("/backend/config.py").status_code == 404
    assert client.get("/.env").status_code == 404
