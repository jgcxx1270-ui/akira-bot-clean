# analyzer.py — módulo para análisis de imágenes y documentos en Akira
import os
from io import BytesIO
from openai import OpenAI
from pdfminer.high_level import extract_text
from docx import Document
from PIL import Image

# ----- OCR opcional (no rompe si no hay Tesseract) -----
OCR_AVAILABLE = False
try:
    import pytesseract
    OCR_AVAILABLE = True
except Exception:
    pass

# Inicializa cliente OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ---- OCR desde bytes ----
def ocr_from_bytes(data: bytes, lang: str = "spa"):
    """Realiza OCR sobre una imagen si Tesseract está disponible."""
    if not OCR_AVAILABLE:
        return "[OCR] No disponible en este entorno."
    try:
        img = Image.open(BytesIO(data))
        text = pytesseract.image_to_string(img, lang=lang)
        return text.strip()
    except Exception as e:
        return f"[OCR] Error: {e}"

# ---- OpenAI Visión ----
def analyze_image_bytes(media_type: str, data: bytes, goal: str = "Describe la imagen."):
    """Usa el modelo de visión de OpenAI para analizar imágenes o fotos."""
    try:
        import base64
        img_b64 = base64.b64encode(data).decode("utf-8")
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Eres Akira, una mascota IA que analiza imágenes de manera útil y amigable."},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": goal},
                        {"type": "image_url", "image_url": f"data:{media_type};base64,{img_b64}"}
                    ]
                }
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[Error al analizar imagen: {e}]"

# ---- Procesar documentos ----
def extract_text_from_pdf(data: bytes):
    try:
        from tempfile import NamedTemporaryFile
        with NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(data)
            tmp.flush()
            text = extract_text(tmp.name)
        return text
    except Exception as e:
        return f"[Error extrayendo PDF: {e}]"

def extract_text_from_docx(data: bytes):
    try:
        from tempfile import NamedTemporaryFile
        with NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            tmp.write(data)
            tmp.flush()
            doc = Document(tmp.name)
            return "\n".join(p.text for p in doc.paragraphs)
    except Exception as e:
        return f"[Error leyendo DOCX: {e}]"

def handle_document_bytes(media_type: str, data: bytes, mode: str = "resumen"):
    """Lee documentos PDF/DOCX/TXT y pide a OpenAI un resumen o explicación."""
    text = ""
    if "pdf" in media_type:
        text = extract_text_from_pdf(data)
    elif "word" in media_type or "docx" in media_type:
        text = extract_text_from_docx(data)
    else:
        try:
            text = data.decode("utf-8", errors="ignore")
        except Exception:
            text = "[No se pudo leer el archivo.]"

    if not text.strip():
        return ["[No se pudo extraer texto del documento.]"]

    prompt = "Resume el contenido del documento brevemente." if mode == "resumen" else "Explica detalladamente el contenido del documento."

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Eres Akira, una IA útil y amigable."},
                {"role": "user", "content": f"{prompt}\n\nTexto:\n{text[:10000]}"},
            ]
        )
        reply = response.choices[0].message.content.strip()
        return split_for_whatsapp(reply)
    except Exception as e:
        return [f"[Error procesando documento: {e}]"]

# ---- Dividir respuestas largas ----
def split_for_whatsapp(text: str, max_chars: int = 1400):
    """Divide texto en partes para evitar el límite de Twilio/WhatsApp."""
    parts = []
    while len(text) > max_chars:
        cut = text[:max_chars]
        last_period = cut.rfind(". ")
        if last_period != -1:
            cut = cut[:last_period+1]
        parts.append(cut.strip())
        text = text[len(cut):]
    if text.strip():
        parts.append(text.strip())
    return parts
