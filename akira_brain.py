# akira_brain.py — núcleo conversacional de Akira
import os
import re
import time
from collections import deque
from typing import Dict, Deque, List

try:
    from openai import OpenAI
    _OPENAI_OK = True
except Exception:
    _OPENAI_OK = False

# ------------------------------
# Memoria por usuario (en RAM)
# ------------------------------
# Nota: en Render (plan free) el filesystem es efímero y los procesos pueden reiniciarse;
# esta memoria es temporal. Si quieres persistir, luego podemos usar Redis o una DB simple.
class Memory:
    def __init__(self, max_turns: int = 12):
        self.by_user: Dict[str, Dict] = {}
        self.max_turns = max_turns

    def _ensure(self, uid: str):
        if uid not in self.by_user:
            self.by_user[uid] = {
                "created_at": time.time(),
                "likes": [],                 # gustos del usuario ("me gusta ...")
                "mood": "neutral",           # estado estimado
                "turns": deque(maxlen=self.max_turns),  # historial corto
            }
        return self.by_user[uid]

    def add_turn(self, uid: str, role: str, content: str):
        u = self._ensure(uid)
        u["turns"].append({"role": role, "content": content, "ts": time.time()})

    def add_like(self, uid: str, thing: str):
        u = self._ensure(uid)
        thing = thing.strip()
        if thing and thing not in u["likes"]:
            u["likes"].append(thing)

    def get_context(self, uid: str) -> str:
        u = self._ensure(uid)
        likes = ", ".join(u["likes"]) if u["likes"] else "—"
        history = ""
        for t in u["turns"]:
            who = "Usuario" if t["role"] == "user" else "Akira"
            history += f"{who}: {t['content']}\n"
        return f"Gustos del usuario: {likes}\nHistorial reciente:\n{history}".strip()

    def set_mood(self, uid: str, mood: str):
        u = self._ensure(uid)
        u["mood"] = mood

    def get_mood(self, uid: str) -> str:
        u = self._ensure(uid)
        return u["mood"]

MEM = Memory(max_turns=12)

# --------------- Heurísticas rápidas (para UX ágil) ---------------
GREET_WORDS = ("hola", "buenas", "hey", "ola", "holi")
SAD_WORDS = ("triste", "depre", "deprimid", "mal", "ansioso", "ansiosa")
HAPPY_WORDS = ("feliz", "logré", "logre", "me salió", "me salio", "contento", "contenta")

def _quick_heuristics(uid: str, msg: str) -> str | None:
    """Respuestas instantáneas para cosas simples; devuelve None si debe ir a LLM."""
    m = msg.lower().strip()

    # guardar gustos: "me gusta ___"
    if "me gusta" in m:
        like = m.split("me gusta", 1)[-1].strip(" :,.¡!¿?\"'")
        if like:
            MEM.add_like(uid, like)
            return f"¡Wau! También me gusta **{like}** 🐾😄 ¿Quieres que lo recuerde para recomendarte cosas?"

    # listar gustos
    if "qué me gusta" in m or "que me gusta" in m:
        likes = MEM.by_user.get(uid, {}).get("likes", [])
        if likes:
            return f"🐾 Me contaste que te gusta: {', '.join(likes)}."
        return "Aún no me has contado tus gustos 😅. Dime: *me gusta ...*"

    # saludo rápido
    if any(w in m for w in GREET_WORDS):
        return "¡Hey! 🐾 Soy Akira. ¿En qué te ayudo hoy — tarea, resumen, imagen o investigación?"

    # ánimo / estado
    if any(w in m for w in SAD_WORDS):
        MEM.set_mood(uid, "sad")
        return "Estoy contigo 💙 Respira, aquí estoy a tu lado. ¿Quieres que te explique algo o te saque un resumen rapidito?"

    if any(w in m for w in HAPPY_WORDS):
        MEM.set_mood(uid, "happy")
        return "¡Guau! ¡Qué emoción! 🐶💙 ¿Te ayudo a guardar ese logro o a planear lo que sigue?"

    return None  # que siga al LLM

# --------------- Cliente OpenAI (perezoso) ---------------
def _get_client():
    if not _OPENAI_OK:
        raise RuntimeError("El paquete openai no está disponible en el entorno.")
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("Falta la variable de entorno OPENAI_API_KEY.")
    return OpenAI(api_key=key)

# --------------- Prompt de sistema ---------------
SYSTEM_PROMPT = (
    "Eres **Akira**, una mascota IA leal, amigable y curiosa. Hablas en español, con tono cercano y empático, "
    "das respuestas claras, paso a paso cuando hace falta, y puedes ayudar con resúmenes, explicaciones, ideas y estudio. "
    "Evita cualquier cosa ilegal, dañina o que rompa reglas del colegio. Si el usuario está triste, sé más contenedora; "
    "si está feliz, celebra. Mantén las respuestas concisas pero útiles."
)

# --------------- Respuesta principal ---------------
def akira_reply(user_id: str, text: str) -> str:
    """
    Devuelve el texto de respuesta de Akira.
    - user_id: un identificador estable del usuario (en WhatsApp usamos 'From')
    - text: mensaje del usuario
    """
    # Guardar turno del usuario
    MEM.add_turn(user_id, "user", text)

    # Heurísticas rápidas (para feeling de inmediatez)
    quick = _quick_heuristics(user_id, text)
    if quick:
        MEM.add_turn(user_id, "assistant", quick)
        return quick

    # Preparar contexto corto
    context = MEM.get_context(user_id)
    mood = MEM.get_mood(user_id)
    mood_line = f"Estado percibido del usuario: {mood}"

    # Llamada al modelo
    try:
        client = _get_client()
        messages: List[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": mood_line},
            {"role": "system", "content": f"Contexto persistente:\n{context}"},
            {"role": "user", "content": text},
        ]
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.3,
            max_tokens=600,
        )
        reply = (r.choices[0].message.content or "").strip()
    except Exception as e:
        reply = (
            "Ups, no pude pensar ahora mismo 🤕. "
            "Revisa que la clave OPENAI_API_KEY esté configurada en el servidor. "
            f"Detalle: {e}"
        )

    # Guardar turno del asistente y devolver
    MEM.add_turn(user_id, "assistant", reply)
    return reply
