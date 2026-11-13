# Proyecto Indus — Traductor de Texto y Documentos PDF

**Indus** es una aplicación web académica que ofrece dos funcionalidades principales:
1. **Traductor de texto**: Traducción bidireccional entre inglés y español mediante modelos de lenguaje a través de OpenRouter.
2. **Traductor de archivos PDF**: Carga de documentos PDF (hasta 10 MB y 20 páginas), extracción inteligente página por página (texto seleccionable con PyMuPDF, páginas escaneadas con Tesseract OCR y documentos híbridos), traducción por fragmentos con OpenRouter, generación de un nuevo PDF legible con ReportLab, vista previa integrada y descarga del documento final.

---

## 1. Estructura del Proyecto

```text
Indus/
│
├── backend/
│   ├── __init__.py
│   ├── app.py                     # Servidor Flask, inyección no invasiva de JS y rutas
│   ├── config.py                  # Configuración centralizada y lectura de .env
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── text_routes.py         # Endpoint POST /api/translate
│   │   └── pdf_routes.py          # Endpoints de validación, traducción, vista previa y descarga PDF
│   ├── services/
│   │   ├── __init__.py
│   │   ├── translation_service.py # Integración con OpenRouter y división por fragmentos
│   │   ├── pdf_extraction.py      # Extracción con PyMuPDF + detección híbrida/escaneada
│   │   ├── ocr_service.py         # Preprocesamiento con Pillow y reconocimiento con Tesseract OCR
│   │   ├── pdf_generator.py       # Generación del PDF traducido con ReportLab
│   │   └── job_manager.py         # Gestión de trabajos, estados y limpieza de archivos temporales
│   ├── utils/
│   │   ├── __init__.py
│   │   └── validators.py          # Validaciones de texto, idiomas y seguridad estructural de PDF
│   ├── tests/
│   │   └── test_indus_backend.py  # Suite de pruebas automatizadas (pytest)
│   └── requirements.txt           # Dependencias de Python
│
├── Archivos/                      # Recursos gráficos del frontend
├── .env.example                   # Plantilla de variables de entorno (sin credenciales reales)
├── .gitignore                     # Exclusión de .env, entornos virtuales y temporales
├── README.md                      # Documentación del proyecto
├── index.html                     # Página de inicio (intacta)
├── traductor-texto.html           # Interfaz del traductor de texto (intacta)
├── traductor-archivos.html        # Interfaz del traductor de archivos y visor (intacta)
├── estilo.css                     # Estilos de inicio (intacto)
├── estilo-texto.css               # Estilos de traductor de texto (intacto)
├── estilo-archivos.css            # Estilos de traductor de archivos (intacto)
└── javascript.js                  # Lógica frontend conectada a los endpoints REST del backend
```

> **Nota sobre la preservación del Frontend (Opción 1):** Los archivos `index.html`, `traductor-texto.html`, `traductor-archivos.html`, `estilo.css`, `estilo-texto.css` y `estilo-archivos.css` permanecen **100 % intactos en disco**. El servidor Flask sirve las páginas HTML e inyecta en memoria la etiqueta `<script src="javascript.js"></script>` antes de `</body>`.

---

## 2. Instalación y Ejecución en Windows

### 2.1 Requisitos previos
- **Python 3.10 o superior** (en este entorno ya se incluye Python 3.12).
- **Tesseract OCR** (necesario para páginas escaneadas o documentos híbridos con imágenes).
- Una cuenta y **API Key de OpenRouter** ([https://openrouter.ai/](https://openrouter.ai/)).

### 2.2 Crear el entorno virtual e instalar dependencias

Abre **PowerShell** en la carpeta raíz del proyecto (`c:\Users\lf201\Documents\Indus`):

```powershell
# Opción A: Usando Python estándar
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt

# Opción B: Usando uv (si está instalado en el sistema)
uv venv .venv
uv pip install -r backend/requirements.txt --python .venv\Scripts\python.exe
```

---

## 3. Instalación y Configuración de Tesseract OCR en Windows

Para procesar documentos PDF escaneados o híbridos:

1. **Instalar Tesseract OCR en Windows:**
   - **Mediante Winget (recomendado desde PowerShell):**
     ```powershell
     winget install --id UB-Mannheim.TesseractOCR
     ```
   - **Mediante el instalador oficial de UB-Mannheim:**
     Descarga el instalador desde [https://github.com/UB-Mannheim/tesseract/wiki](https://github.com/UB-Mannheim/tesseract/wiki) y durante la instalación marca los paquetes de idioma **English (`eng`)** y **Spanish (`spa`)** en *Additional script/language data*.

2. **Configurar la ruta para Python:**
   - El backend busca automáticamente Tesseract en:
     1. La variable `TESSERACT_CMD` definida en `.env`.
     2. El `PATH` del sistema Windows.
     3. Rutas habituales (`C:\Program Files\Tesseract-OCR\tesseract.exe`, `C:\Program Files (x86)\Tesseract-OCR\tesseract.exe`, `%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe`).
   - Si instalaste Tesseract en una ruta personalizada, agrégala en tu archivo `.env`:
     ```env
     TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
     ```

3. **Comprobar que Python localiza Tesseract correctamente:**
   Con el servidor en marcha, consulta `http://127.0.0.1:5000/api/health` o ejecuta en PowerShell:
   ```powershell
   .\.venv\Scripts\python.exe -c "from backend.services.ocr_service import is_tesseract_available, resolve_tesseract_executable; print('Disponible:', is_tesseract_available(), '| Ruta:', resolve_tesseract_executable())"
   ```

---

## 4. Configuración de OpenRouter (`.env`)

1. Copia el archivo `.env.example` a `.env` en la raíz del proyecto:
   ```powershell
   Copy-Item .env.example .env
   ```
2. Edita el archivo `.env` y coloca tu clave real y el modelo que desees utilizar en OpenRouter:
   ```env
   OPENROUTER_API_KEY=sk-or-v1-tu_clave_real_aqui
   OPENROUTER_MODEL=openai/gpt-4o-mini
   OPENROUTER_API_URL=https://openrouter.ai/api/v1/chat/completions
   OPENROUTER_TIMEOUT=60
   FLASK_DEBUG=True
   FLASK_HOST=127.0.0.1
   FLASK_PORT=5000
   ```
   - Puedes cambiar `OPENROUTER_MODEL` en cualquier momento (por ejemplo, `google/gemini-2.0-flash-001`, `anthropic/claude-3.5-haiku`, `meta-llama/llama-3.3-70b-instruct`, etc.) sin modificar ni una sola línea de código.
   - La API Key se mantiene exclusivamente en el backend y nunca se envía al navegador ni se registra en logs.

---

## 5. Ejecución del Servidor Flask

Desde la raíz del proyecto (`c:\Users\lf201\Documents\Indus`):

```powershell
.\.venv\Scripts\python.exe backend/app.py
```

Luego abre en tu navegador:
- **Inicio:** `http://127.0.0.1:5000/`
- **Traductor de texto:** `http://127.0.0.1:5000/traductor-texto.html`
- **Traductor de archivos PDF:** `http://127.0.0.1:5000/traductor-archivos.html`

---

## 6. Documentación de los Endpoints REST

### 6.1 `GET /api/health`
Comprueba el estado del servidor y la disponibilidad de OpenRouter y Tesseract OCR (sin exponer credenciales).
- **Respuesta `200 OK`:**
  ```json
  {
    "status": "ok",
    "service": "Indus Backend",
    "openrouter_configured": true,
    "openrouter_model": "openai/gpt-4o-mini",
    "tesseract_available": true,
    "tesseract_path": "C:\\Program Files\\Tesseract-OCR\\tesseract.exe",
    "limits": {
      "max_file_size_mb": 10,
      "max_pdf_pages": 20
    }
  }
  ```

### 6.2 `POST /api/translate`
Traduce texto entre inglés y español mediante OpenRouter.
- **Formato de entrada (`application/json`):**
  ```json
  {
    "text": "Hello world, this is a document.",
    "source_lang": "Inglés",
    "target_lang": "Español"
  }
  ```
  *(Acepta `"Inglés"` / `"en"` y `"Español"` / `"es"`).*
- **Respuesta exitosa (`200 OK`):**
  ```json
  {
    "status": "ok",
    "original_text": "Hello world, this is a document.",
    "translated_text": "Hola mundo, este es un documento.",
    "source_lang": "en",
    "target_lang": "es",
    "source_lang_name": "Inglés",
    "target_lang_name": "Español"
  }
  ```
- **Códigos de error:**
  - `400 Bad Request`: Texto vacío (`EMPTY_TEXT`), idiomas iguales (`SAME_LANGUAGE`) o JSON inválido (`INVALID_JSON`).
  - `429 Too Many Requests`: Límite de peticiones de OpenRouter alcanzado (`API_RATE_LIMIT`).
  - `502 Bad Gateway`: Error de conexión o respuesta inválida de OpenRouter (`API_CONNECTION_ERROR`, `API_INVALID_STRUCTURE`).
  - `503 Service Unavailable`: `OPENROUTER_API_KEY` o `OPENROUTER_MODEL` no configurados en `.env`.
  - `504 Gateway Timeout`: Tiempo de espera agotado con OpenRouter (`API_TIMEOUT`).

### 6.3 `POST /api/translate/pdf/validate`
Valida la integridad, extensión, tamaño (máx. 10 MB) y número de páginas (máx. 20) de un PDF seleccionado antes de iniciar la traducción.
- **Formato de entrada:** `multipart/form-data` con campo `file`.
- **Respuesta exitosa (`200 OK`):**
  ```json
  {
    "status": "ok",
    "filename": "informe.pdf",
    "safe_stem": "informe",
    "file_size_bytes": 245812,
    "page_count": 8
  }
  ```
- **Códigos de error:** `400` (`NO_FILE`, `INVALID_EXTENSION`, `INVALID_PDF_HEADER`, `CORRUPTED_PDF`, `ENCRYPTED_PDF`, `TOO_MANY_PAGES`), `413` (`FILE_TOO_LARGE`).

### 6.4 `POST /api/translate/pdf`
Recibe un archivo PDF, extrae su contenido (directo con PyMuPDF, OCR con Tesseract o híbrido página por página), traduce por fragmentos con OpenRouter y genera el nuevo PDF con ReportLab.
- **Formato de entrada (`multipart/form-data`):**
  - `file`: Archivo PDF (obligatorio, máx. 10 MB, máx. 20 páginas).
  - `source_lang`: `"Inglés"` o `"en"` (por defecto `"en"`).
  - `target_lang`: `"Español"` o `"es"` (por defecto `"es"`).
  - `async`: `"true"` (inicia procesamiento en segundo plano y responde `202 Accepted` para consultar progreso en tiempo real) o `"false"` (por defecto, ejecuta síncronamente y responde `200 OK` al terminar).
- **Respuesta (`200 OK` o `202 Accepted`):**
  ```json
  {
    "job_id": "a1b2c3d4e5f678901234567890abcdef",
    "status": "completed",
    "step": "completed",
    "status_message": "Proceso completado.",
    "progress": 100,
    "original_filename": "informe.pdf",
    "output_filename": "informe-es.pdf",
    "file_size_bytes": 245812,
    "source_lang": "en",
    "target_lang": "es",
    "source_lang_name": "Inglés",
    "target_lang_name": "Español",
    "source_pages_count": 2,
    "output_pages_count": 2,
    "document_type": "selectable",
    "used_ocr": false,
    "error": null,
    "error_code": null,
    "download_url": "/api/translate/pdf/a1b2c3d4e5f678901234567890abcdef/download",
    "view_url": "/api/translate/pdf/a1b2c3d4e5f678901234567890abcdef/view",
    "pages_preview": [
      {
        "page_number": 1,
        "translated_text": "RESUMEN EJECUTIVO...",
        "method": "direct"
      }
    ]
  }
  ```

### 6.5 `GET /api/translate/pdf/<job_id>`
Consulta el estado en tiempo real (`received`, `validating`, `extracting`, `ocr`, `translating`, `generating`, `completed`, `error`) y los metadatos del documento procesado.

### 6.6 `GET /api/translate/pdf/<job_id>/download`
Descarga el documento PDF traducido (`Content-Type: application/pdf`, `Content-Disposition: attachment`).

### 6.7 `GET /api/translate/pdf/<job_id>/view` y `GET /api/translate/pdf/<job_id>/page/<page_num>`
- `/view`: Entrega el PDF traducido en línea (`inline`).
- `/page/<page_num>`: Renderiza la página `<page_num>` del PDF traducido como imagen PNG (`160 DPI`) para alimentar el visor integrado de `traductor-archivos.html` con soporte de paginación (`◀`/`▶`) y zoom (`−`/`+`).

---

## 7. Ejecución de Pruebas Automatizadas

Para ejecutar las 16 pruebas automatizadas que cubren todos los escenarios de texto y archivos PDF:

```powershell
.\.venv\Scripts\pytest.exe backend/tests/test_indus_backend.py -v
```
