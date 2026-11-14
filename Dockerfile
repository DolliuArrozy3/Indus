
FROM python:3.12-slim

# Directorio de trabajo
WORKDIR /app

# Instalar Tesseract OCR y los idiomas inglés y español
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-spa \
    && rm -rf /var/lib/apt/lists/*

# Configurar ubicación de Tesseract
ENV TESSERACT_CMD=/usr/bin/tesseract

# Instalar dependencias Python
COPY backend/requirements.txt ./backend/requirements.txt

RUN pip install --no-cache-dir -r backend/requirements.txt

# Copiar el proyecto completo
COPY . .

# Puerto de la aplicación
EXPOSE 10000

# Ejecutar Flask mediante Gunicorn
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-10000} backend.app:app"]
