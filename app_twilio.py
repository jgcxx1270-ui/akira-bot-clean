# app_twilio.py — Akira WhatsApp (IA + docs + imágenes) sin eco, robusto
import os
import requests
from flask import Flask, request, Response
from dotenv import load_dotenv
from twilio.twiml.messaging_response import MessagingResponse

from akira_brain import akira_reply
from analyzer import analyze_image_bytes, handle_document_bytes, split_for_whatsapp

load_dotenv()
app = Flask(__name__)

# Credenciales para descargar media protegida desde Twilio
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN")

@app.route("/whatsapp", methods=["POST", "GET"])
def whatsapp_webhook():
    # GET solo para verificar rápido desde el navegador
    if request.method == "GET":
        return "Akira WhatsApp webhook vivo (usa POST desde Twilio)", 200

    resp = MessagingResponse()
    try:
        form = request.form
        from_number = form.get("From", "")
        body        = form.get("Body", "") or ""
        num_media   = int(form.get("NumMedia", "0") or 0)

        # Logs útiles (se ven en Render → Logs)
        print(">>> HIT /whatsapp")
        print(">>> FROM:", from_number)
        print(">>> BODY:", body)
        print(">>> NUM_MEDIA:", num_media)

        # 1) Si viene archivo (imagen/pdf/docx/txt) lo procesamos
        if num_media > 0:
            media_url = form.get("MediaUrl0")
            media_ct  = form.get("MediaContentType0", "")
            print(">>> MEDIA:", media_url, media_ct)

            # Descargar media con auth (requerido por Twilio)
            r = requests.get(media_url, auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN), timeout=30)
            r.raise_for_status()
            data = r.content

            # Imagen → visión (y OCR si está disponible dentro de analyzer)
            if media_ct.startswith("image/"):
                # Si el usuario escribió algo junto con la imagen, úsalo como objetivo
                goal = body.strip() or "Analiza y resuelve si es una tarea; explica paso a paso."
                out_text = analyze_image_bytes(media_ct, data, goal=goal)
                parts = split_for_whatsapp(out_text)
            else:
                # Documento → sacamos texto y pedimos resumen/explicación
                mode = "resumen"
                bl = body.lower()
                if any(k in bl for k in ["explica", "explícame", "explicame", "explicar"]):
                    mode = "explicar"
                parts = handle_document_bytes(media_ct, data, mode=mode)

            for p in parts:
                resp.message(p)
            return Response(str(resp), mimetype="application/xml", status=200)

        # 2) Texto normal → pasa por el cerebro de Akira (memoria ligera por usuario)
        reply = akira_reply(from_number, body)
        for p in split_for_whatsapp(reply):
            resp.message(p)
        return Response(str(resp), mimetype="application/xml", status=200)

    except Exception as e:
        # Pase lo que pase, respondemos 200 (evita timeout 11200 en Twilio)
        print(">>> ERROR en /whatsapp:", repr(e))
        resp.message(f"Ups, tuve un problema procesando tu mensaje 🤕\nDetalle: {e}")
        return Response(str(resp), mimetype="application/xml", status=200)

@app.route("/", methods=["GET"])
def home():
    return "Akira WhatsApp Bot ON v2 ✅", 200

@app.route("/healthz", methods=["GET"])
def health():
    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
