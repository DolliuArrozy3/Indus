import os
import re
from pathlib import Path
from typing import List, Dict, Any
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    PageBreak,
    HRFlowable,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


class PDFGenerationError(Exception):
    """Excepción para errores durante la generación del PDF traducido."""

    def __init__(self, message: str, status_code: int = 500, code: str = "PDF_GENERATION_ERROR"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


def _register_unicode_fonts() -> tuple[str, str]:
    """
    Intenta registrar una fuente TrueType del sistema (Arial o Segoe UI)
    para soporte completo de caracteres Unicode en español.
    Si no está disponible, utiliza Helvetica estándar.
    """
    font_candidates = [
        (
            "IndusSans",
            "IndusSans-Bold",
            r"C:\Windows\Fonts\arial.ttf",
            r"C:\Windows\Fonts\arialbd.ttf",
        ),
        (
            "IndusSans",
            "IndusSans-Bold",
            r"C:\Windows\Fonts\segoeui.ttf",
            r"C:\Windows\Fonts\segoeuib.ttf",
        ),
    ]

    for reg_name, bold_name, reg_path, bold_path in font_candidates:
        if os.path.isfile(reg_path) and os.path.isfile(bold_path):
            try:
                if reg_name not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont(reg_name, reg_path))
                if bold_name not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont(bold_name, bold_path))
                return reg_name, bold_name
            except Exception:
                continue

    return "Helvetica", "Helvetica-Bold"


def _draw_page_header_footer(canvas, doc):
    """Dibuja un encabezado sutil y número de página en cada hoja generada."""
    canvas.saveState()
    font_name = "Helvetica"
    canvas.setFont(font_name, 8.5)
    canvas.setFillColor(colors.HexColor("#718096"))

    width, height = A4
    # Encabezado superior
    canvas.drawString(2.2 * cm, height - 1.3 * cm, "INDUS — Documento Traducido")
    canvas.setStrokeColor(colors.HexColor("#E2E8F0"))
    canvas.setLineWidth(0.5)
    canvas.line(2.2 * cm, height - 1.5 * cm, width - 2.2 * cm, height - 1.5 * cm)

    # Pie de página con numeración
    page_label = f"Página {doc.page}"
    canvas.drawRightString(width - 2.2 * cm, 1.2 * cm, page_label)
    canvas.restoreState()


def _format_inline_markdown(escaped_text: str) -> str:
    """Convierte negritas básicas **texto** en etiquetas <b>texto</b> seguras para ReportLab."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped_text)


def generate_translated_pdf(
    translated_pages: List[Dict[str, Any]],
    output_path: Path,
    title: str = "Documento Traducido - Indus",
) -> Dict[str, Any]:
    """
    Genera un archivo PDF limpio, legible y bien estructurado a partir de las
    páginas traducidas utilizando ReportLab.

    Parámetros:
    - translated_pages: Lista de dicts con {'page_number': int, 'translated_text': str}
    - output_path: Ruta donde se guardará el PDF generado.
    """
    if not translated_pages:
        raise PDFGenerationError(
            "No hay contenido traducido para generar el documento PDF.",
            422,
            "EMPTY_TRANSLATED_PAGES",
        )

    font_regular, font_bold = _register_unicode_fonts()

    styles = getSampleStyleSheet()

    heading_style = ParagraphStyle(
        "IndusHeading",
        parent=styles["Heading2"],
        fontName=font_bold,
        fontSize=13.5,
        leading=18,
        textColor=colors.HexColor("#111111"),
        spaceBefore=10,
        spaceAfter=8,
        alignment=TA_LEFT,
    )

    subheading_style = ParagraphStyle(
        "IndusSubHeading",
        parent=styles["Heading3"],
        fontName=font_bold,
        fontSize=11.5,
        leading=15,
        textColor=colors.HexColor("#1A202C"),
        spaceBefore=8,
        spaceAfter=6,
        alignment=TA_LEFT,
    )

    body_style = ParagraphStyle(
        "IndusBody",
        parent=styles["BodyText"],
        fontName=font_regular,
        fontSize=10.5,
        leading=15.5,
        textColor=colors.HexColor("#1A202C"),
        spaceBefore=0,
        spaceAfter=9,
        alignment=TA_JUSTIFY,
    )

    list_style = ParagraphStyle(
        "IndusList",
        parent=body_style,
        leftIndent=16,
        firstLineIndent=-10,
        spaceAfter=5,
        alignment=TA_LEFT,
    )

    page_marker_style = ParagraphStyle(
        "IndusPageMarker",
        parent=styles["Normal"],
        fontName=font_bold,
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#718096"),
        spaceBefore=0,
        spaceAfter=8,
    )

    story = []
    total_source_pages = len(translated_pages)

    for idx, page_data in enumerate(translated_pages):
        page_num = page_data.get("page_number", idx + 1)
        text = (page_data.get("translated_text") or "").strip()

        if idx > 0:
            story.append(PageBreak())

        if total_source_pages > 1:
            story.append(Paragraph(f"SECCIÓN DE PÁGINA ORIGINAL {page_num}", page_marker_style))
            story.append(
                HRFlowable(
                    width="100%",
                    thickness=0.5,
                    color=colors.HexColor("#CBD5E0"),
                    spaceBefore=2,
                    spaceAfter=10,
                )
            )

        if not text:
            story.append(Paragraph("<i>[Página sin texto traducible]</i>", body_style))
            continue

        # Normalizar saltos de línea y procesar bloques de párrafo
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        raw_blocks = re.split(r"\n\s*\n", normalized)

        for block in raw_blocks:
            block_stripped = block.strip()
            if not block_stripped:
                continue

            lines = [ln.strip() for ln in block_stripped.split("\n") if ln.strip()]
            if not lines:
                continue

            # Verificar si el bloque es una lista de elementos
            is_list_block = all(
                re.match(r"^(\-|\*|•|\d+[\.\)])\s+", ln) for ln in lines
            )

            if is_list_block:
                for ln in lines:
                    cleaned_item = re.sub(r"^(\-|\*|•)\s+", "• ", ln)
                    escaped_item = _format_inline_markdown(escape(cleaned_item))
                    story.append(Paragraph(escaped_item, list_style))
                story.append(Spacer(1, 4))
                continue

            # Verificar si la primera línea es un encabezado
            first_line = lines[0]
            is_markdown_h1_h2 = first_line.startswith("# ") or first_line.startswith("## ")
            is_markdown_h3 = first_line.startswith("### ")
            is_upper_heading = (
                len(lines) == 1
                and 3 <= len(first_line) <= 85
                and first_line.isupper()
                and not first_line.endswith(".")
            )

            if is_markdown_h1_h2 or is_upper_heading:
                clean_title = re.sub(r"^#+\s*", "", first_line).strip()
                story.append(Paragraph(_format_inline_markdown(escape(clean_title)), heading_style))
                if len(lines) > 1:
                    rest_escaped = "<br/>".join(_format_inline_markdown(escape(ln)) for ln in lines[1:])
                    story.append(Paragraph(rest_escaped, body_style))
            elif is_markdown_h3:
                clean_sub = re.sub(r"^#+\s*", "", first_line).strip()
                story.append(Paragraph(_format_inline_markdown(escape(clean_sub)), subheading_style))
                if len(lines) > 1:
                    rest_escaped = "<br/>".join(_format_inline_markdown(escape(ln)) for ln in lines[1:])
                    story.append(Paragraph(rest_escaped, body_style))
            else:
                # Procesar líneas dentro del párrafo (pueden incluir sub-listas o líneas normales)
                para_buffer: List[str] = []
                for ln in lines:
                    if re.match(r"^(\-|\*|•|\d+[\.\)])\s+", ln):
                        if para_buffer:
                            story.append(Paragraph("<br/>".join(para_buffer), body_style))
                            para_buffer = []
                        cleaned_item = re.sub(r"^(\-|\*|•)\s+", "• ", ln)
                        story.append(Paragraph(_format_inline_markdown(escape(cleaned_item)), list_style))
                    else:
                        para_buffer.append(_format_inline_markdown(escape(ln)))
                if para_buffer:
                    story.append(Paragraph("<br/>".join(para_buffer), body_style))

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            leftMargin=2.2 * cm,
            rightMargin=2.2 * cm,
            topMargin=2.2 * cm,
            bottomMargin=2.0 * cm,
            title=title,
            author="Indus Translator",
        )
        doc.build(
            story,
            onFirstPage=_draw_page_header_footer,
            onLaterPages=_draw_page_header_footer,
        )
    except Exception as exc:
        raise PDFGenerationError(
            f"Error al generar el documento PDF traducido: {str(exc)[:150]}",
            500,
            "REPORTLAB_BUILD_ERROR",
        )

    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise PDFGenerationError(
            "El archivo PDF traducido no se generó correctamente.",
            500,
            "EMPTY_GENERATED_PDF",
        )

    return {
        "output_path": str(output_path),
        "file_size_bytes": output_path.stat().st_size,
    }
