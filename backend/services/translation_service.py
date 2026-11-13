import logging
import re
from typing import List
import requests

from backend.config import Config
from backend.utils.validators import LANGUAGE_NAMES

logger = logging.getLogger(__name__)

PLACEHOLDER_KEYS = {
    "",
    "tu_api_key",
    "tu_api_key_aqui",
    "your_api_key",
    "your_api_key_here",
}

PLACEHOLDER_MODELS = {
    "",
    "modelo_seleccionado",
    "tu_modelo",
}


class TranslationError(Exception):
    """Excepción para errores durante la traducción con OpenRouter."""

    def __init__(self, message: str, status_code: int = 502, code: str = "TRANSLATION_ERROR"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


def check_openrouter_credentials() -> tuple[str, str, str]:
    """Verifica que la API Key y el modelo de OpenRouter estén configurados."""
    api_key = Config.get_openrouter_api_key()
    model = Config.get_openrouter_model()
    api_url = Config.get_openrouter_url()

    if not api_key or api_key.lower() in PLACEHOLDER_KEYS:
        raise TranslationError(
            "La API Key de OpenRouter no está configurada. Configura OPENROUTER_API_KEY en el archivo .env del servidor.",
            503,
            "MISSING_API_KEY",
        )

    if not model or model.lower() in PLACEHOLDER_MODELS:
        raise TranslationError(
            "El modelo de OpenRouter no está configurado. Configura OPENROUTER_MODEL en el archivo .env del servidor.",
            503,
            "MISSING_MODEL",
        )

    return api_key, model, api_url


def split_text_into_chunks(text: str, max_chars: int = None) -> List[str]:
    """
    Divide un texto largo en fragmentos respetando saltos de párrafo y oraciones
    para no superar los límites de contexto del modelo y mantener el orden original.
    """
    if max_chars is None:
        max_chars = Config.MAX_CHUNK_CHARS

    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    if len(cleaned) <= max_chars:
        return [cleaned]

    paragraphs = cleaned.split("\n\n")
    chunks: List[str] = []
    current_chunk: List[str] = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para)
        sep_len = 2 if current_chunk else 0

        if current_len + sep_len + para_len <= max_chars:
            current_chunk.append(para)
            current_len += sep_len + para_len
        else:
            if current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = []
                current_len = 0

            if para_len <= max_chars:
                current_chunk.append(para)
                current_len = para_len
            else:
                # Si un párrafo individual excede max_chars, dividir por líneas u oraciones
                lines = para.split("\n")
                sub_chunk: List[str] = []
                sub_len = 0
                for line in lines:
                    if len(line) > max_chars:
                        # Dividir por oraciones o corte seguro
                        sentences = re.split(r"(?<=[.!?])\s+", line)
                        for sent in sentences:
                            if len(sent) > max_chars:
                                for i in range(0, len(sent), max_chars):
                                    if sub_chunk:
                                        chunks.append("\n".join(sub_chunk))
                                        sub_chunk = []
                                        sub_len = 0
                                    chunks.append(sent[i : i + max_chars])
                            elif sub_len + (1 if sub_chunk else 0) + len(sent) <= max_chars:
                                sub_chunk.append(sent)
                                sub_len += (1 if sub_chunk else 0) + len(sent)
                            else:
                                if sub_chunk:
                                    chunks.append(" ".join(sub_chunk))
                                sub_chunk = [sent]
                                sub_len = len(sent)
                    else:
                        sep = 1 if sub_chunk else 0
                        if sub_len + sep + len(line) <= max_chars:
                            sub_chunk.append(line)
                            sub_len += sep + len(line)
                        else:
                            if sub_chunk:
                                chunks.append("\n".join(sub_chunk))
                            sub_chunk = [line]
                            sub_len = len(line)
                if sub_chunk:
                    current_chunk = ["\n".join(sub_chunk)]
                    current_len = len(current_chunk[0])

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return [c for c in chunks if c.strip()]


def translate_single_chunk(
    chunk: str,
    source_lang: str = "en",
    target_lang: str = "es",
    session: requests.Session = None,
) -> str:
    """Envía un único fragmento a OpenRouter y valida la respuesta."""
    if not chunk or not chunk.strip():
        return chunk

    api_key, model, api_url = check_openrouter_credentials()
    timeout = Config.get_openrouter_timeout()

    source_name = LANGUAGE_NAMES.get(source_lang, "Inglés")
    target_name = LANGUAGE_NAMES.get(target_lang, "Español")

    system_prompt = (
        f"Eres un traductor profesional experto de {source_name} a {target_name}. "
        f"Traduce el texto proporcionado por el usuario del {source_name} al {target_name} con total precisión semántica.\n"
        "REGLAS ESTRICTAS:\n"
        "1. Devuelve ÚNICAMENTE el texto traducido, sin introducciones, notas, comentarios ni explicaciones.\n"
        "2. NO resumas, NO omitas ni elimines ninguna parte del contenido original.\n"
        "3. Conserva exactamente la estructura de párrafos, saltos de línea, listas, numeraciones y encabezados.\n"
        "4. Mantén los nombres propios, siglas técnicas o números tal como corresponda en el idioma de destino."
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:5000",
        "X-Title": "Indus Translator",
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": chunk},
        ],
        "temperature": 0.2,
    }

    requester = session if session is not None else requests

    try:
        response = requester.post(
            api_url,
            headers=headers,
            json=payload,
            timeout=timeout,
        )
    except requests.exceptions.Timeout:
        raise TranslationError(
            "Tiempo de espera agotado al conectar con el servicio de traducción (OpenRouter). Inténtalo nuevamente.",
            504,
            "API_TIMEOUT",
        )
    except requests.exceptions.ConnectionError:
        raise TranslationError(
            "Error de conexión con el servidor de OpenRouter. Verifica tu conexión a internet.",
            502,
            "API_CONNECTION_ERROR",
        )
    except requests.exceptions.RequestException:
        raise TranslationError(
            "Error inesperado al comunicarse con el proveedor de traducción.",
            502,
            "API_REQUEST_ERROR",
        )

    if response.status_code == 401:
        raise TranslationError(
            "Credenciales de OpenRouter inválidas (401). Verifica tu OPENROUTER_API_KEY en el archivo .env.",
            502,
            "API_UNAUTHORIZED",
        )
    if response.status_code == 402:
        raise TranslationError(
            "Saldo o créditos insuficientes en la cuenta de OpenRouter (402).",
            502,
            "API_INSUFFICIENT_CREDITS",
        )
    if response.status_code == 429:
        raise TranslationError(
            "Se alcanzó el límite de peticiones de la API de OpenRouter (429). Espera unos segundos e inténtalo de nuevo.",
            429,
            "API_RATE_LIMIT",
        )
    if response.status_code >= 400:
        err_detail = ""
        try:
            err_json = response.json()
            if isinstance(err_json, dict) and "error" in err_json:
                err_obj = err_json["error"]
                if isinstance(err_obj, dict):
                    err_detail = err_obj.get("message", "")
                elif isinstance(err_obj, str):
                    err_detail = err_obj
        except Exception:
            pass
        msg = f"Error del servicio de traducción OpenRouter (HTTP {response.status_code})."
        if err_detail:
            # Asegurar que no se filtre ninguna clave en el mensaje
            safe_detail = re.sub(r"sk-or-[a-zA-Z0-9\-_]+", "[REDACTED]", str(err_detail))
            msg = f"{msg} Detalle: {safe_detail[:180]}"
        raise TranslationError(msg, 502, "API_HTTP_ERROR")

    try:
        data = response.json()
    except ValueError:
        raise TranslationError(
            "El servicio de traducción devolvió una respuesta con formato inválido (no es JSON).",
            502,
            "API_INVALID_JSON",
        )

    if not isinstance(data, dict) or "choices" not in data or not isinstance(data["choices"], list) or len(data["choices"]) == 0:
        raise TranslationError(
            "Respuesta inválida o incompleta de OpenRouter: no se recibieron opciones de traducción.",
            502,
            "API_INVALID_STRUCTURE",
        )

    first_choice = data["choices"][0]
    if not isinstance(first_choice, dict):
        raise TranslationError(
            "Formato de respuesta inesperado en el resultado de OpenRouter.",
            502,
            "API_INVALID_CHOICE",
        )

    # Verificar si la traducción se truncó por límite de tokens
    finish_reason = first_choice.get("finish_reason")
    message_obj = first_choice.get("message")
    if not isinstance(message_obj, dict) or "content" not in message_obj:
        raise TranslationError(
            "Respuesta inválida de OpenRouter: falta el contenido del mensaje traducido.",
            502,
            "API_MISSING_CONTENT",
        )

    translated_text = message_obj.get("content")
    if not isinstance(translated_text, str) or not translated_text.strip():
        raise TranslationError(
            "El modelo de traducción devolvió una respuesta vacía.",
            502,
            "API_EMPTY_TRANSLATION",
        )

    if finish_reason == "length":
        raise TranslationError(
            "La traducción quedó incompleta porque se superó el límite de tokens de salida del modelo.",
            502,
            "API_TRUNCATED_TRANSLATION",
        )

    return translated_text.strip()


def translate_text(text: str, source_lang: str = "en", target_lang: str = "es") -> str:
    """
    Traduce texto completo dividiéndolo en fragmentos si es necesario y
    conservando la estructura de párrafos.
    """
    if not text or not text.strip():
        raise TranslationError("El texto a traducir está vacío.", 400, "EMPTY_TEXT")

    chunks = split_text_into_chunks(text, Config.MAX_CHUNK_CHARS)
    if not chunks:
        raise TranslationError("No se encontró contenido traducible.", 400, "EMPTY_CHUNKS")

    translated_chunks: List[str] = []
    with requests.Session() as session:
        for chunk in chunks:
            translated_part = translate_single_chunk(
                chunk,
                source_lang=source_lang,
                target_lang=target_lang,
                session=session,
            )
            if not translated_part or not translated_part.strip():
                raise TranslationError(
                    "Traducción incompleta: uno de los fragmentos devolvió un resultado vacío.",
                    502,
                    "INCOMPLETE_TRANSLATION",
                )
            translated_chunks.append(translated_part)

    return "\n\n".join(translated_chunks)
