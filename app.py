# app.py
import os
import sqlite3
import io
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Local image libs
try:
    from PIL import Image
    import cv2
    import numpy as np
    HAS_IMG = True
except Exception:
    HAS_IMG = False

load_dotenv()

# --- Config ---
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")  # optional fallback
UPLOAD_FOLDER = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
DB_PATH = os.path.join(os.getcwd(), "medibot.db")
PORT = int(os.getenv("PORT", 5000))

# --- Logging ---
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- AI setup (robust) ---
USE_GEMINI = bool(GEMINI_KEY)
GENAI = None
if USE_GEMINI:
    try:
        try:
            from google import generativeai as genai
        except Exception:
            import google.generativeai as genai
        genai.configure(api_key=GEMINI_KEY)
        GENAI = genai
        logger.info("Gemini client configured")
    except Exception as e:
        logger.exception("Gemini import/config error: %s", e)
        GENAI = None

# Optional OpenAI fallback (if you set OPENAI_KEY)
USE_OPENAI = bool(OPENAI_KEY)
if USE_OPENAI:
    try:
        import openai
        openai.api_key = OPENAI_KEY
        logger.info("OpenAI configured")
    except Exception as e:
        logger.exception("OpenAI config error: %s", e)

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ----- Database helpers -----
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS reminders (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT,
      time TEXT
    )""")
    c.execute("""
    CREATE TABLE IF NOT EXISTS notes (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      content TEXT,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""
    CREATE TABLE IF NOT EXISTS water (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      date TEXT,
      count INTEGER
    )""")
    conn.commit()
    conn.close()

def add_reminder(name, time):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO reminders (name, time) VALUES (?, ?)", (name, time))
    conn.commit()
    conn.close()

def list_reminders():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name, time FROM reminders ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "time": r[2]} for r in rows]

def add_note(content):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO notes (content) VALUES (?)", (content,))
    conn.commit()
    conn.close()

def list_notes(limit=20):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, content, created_at FROM notes ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "content": r[1], "created_at": r[2]} for r in rows]

def get_water_count(date_str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, count FROM water WHERE date = ?", (date_str,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "count": row[1]}
    return None

def set_water_count(date_str, count):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    existing = get_water_count(date_str)
    if existing:
        c.execute("UPDATE water SET count = ? WHERE id = ?", (count, existing["id"]))
    else:
        c.execute("INSERT INTO water (date, count) VALUES (?, ?)", (date_str, count))
    conn.commit()
    conn.close()

# ----- Safe AI helpers -----
def safe_prefix():
    return ("You are Medibot, an educational health assistant. "
            "Always avoid providing medical diagnoses or instructing critical care. "
            "When uncertain, advise the user to consult a licensed healthcare professional.\n\n")

def gemini_generate(prompt, max_output_tokens=512):
    if not GENAI:
        raise RuntimeError("Gemini not configured")
    try:
        # Try newer responses API style
        if hasattr(GENAI, "responses") and hasattr(GENAI.responses, "create"):
            resp = GENAI.responses.create(model="gemini-1.5-flash", input=prompt, max_output_tokens=max_output_tokens)
            if hasattr(resp, "output_text") and resp.output_text:
                return resp.output_text
            # fallback unpack
            out = ""
            for item in getattr(resp, "output", []) or []:
                if isinstance(item, dict):
                    for piece in item.get("content", []):
                        if piece.get("type") == "output_text":
                            out += piece.get("text", "")
            if out:
                return out
            return str(resp)
        # Try older generate/text style
        gen_fn = getattr(GENAI, "generate", None) or getattr(GENAI, "text", None)
        if gen_fn:
            resp = gen_fn(prompt, max_output_tokens=max_output_tokens)
            return getattr(resp, "text", str(resp))
    except Exception as e:
        logger.exception("Gemini call error: %s", e)
        raise
    raise RuntimeError("Unsupported Gemini SDK API surface")

def openai_generate(prompt, max_tokens=400):
    if not USE_OPENAI:
        raise RuntimeError("OpenAI not configured")
    resp = openai.ChatCompletion.create(
        model="gpt-4o-mini" if hasattr(openai, "ChatCompletion") else "gpt-4o",
        messages=[{"role":"user","content":prompt}],
        max_tokens=max_tokens
    )
    return resp.choices[0].message.content.strip()

def generate_text(prompt):
    p = safe_prefix() + prompt
    # prefer Gemini
    if GENAI:
        try:
            return gemini_generate(p)
        except Exception as e:
            logger.warning("Gemini failure, trying OpenAI if configured: %s", e)
    if USE_OPENAI:
        try:
            return openai_generate(p)
        except Exception as e:
            logger.exception("OpenAI failure: %s", e)
    return "AI not available. Please try again later or consult a clinician."

# ----- Image analysis (educational only) -----
def image_describe(path):
    if not HAS_IMG:
        return "Image libraries not installed on the server."
    try:
        img = cv2.imread(path)
        if img is None:
            return "Could not read image."
        h, w = img.shape[:2]
        avg_color = img.mean(axis=(0,1)).astype(int).tolist()
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        n = len(contours)
        desc = f"Educational image description: resolution {w}x{h}. Detected approximately {n} edge-contours. Average BGR color {avg_color}.\n\nNote: This is NOT a diagnosis. For medical interpretation, consult a qualified clinician."
        return desc
    except Exception as e:
        logger.exception("image_describe error: %s", e)
        return f"Image processing error: {e}"

# ----- Routes -----
@app.route("/")
def index():
    return send_from_directory("templates", "index.html")

@app.route("/static/<path:fn>")
def static_files(fn):
    return send_from_directory("static", fn)

@app.route("/.well-known/assetlinks.json")
def serve_assetlinks():
    # Serve the assetlinks.json at the well-known path for TWA verification
    file_path = os.path.join(os.getcwd(), "assetlinks.json")
    if not os.path.exists(file_path):
        return jsonify({"error":"assetlinks.json not found on server"}), 404
    return send_from_directory(os.getcwd(), "assetlinks.json", mimetype="application/json")

@app.route("/healthz")
def healthz():
    return jsonify({"status":"ok"})

@app.route("/api/reminder", methods=["POST"])
def api_add_reminder():
    data = request.json or {}
    name = data.get("name")
    time = data.get("time")
    if not name or not time:
        return jsonify({"error":"missing fields"}), 400
    add_reminder(name, time)
    return jsonify({"ok": True, "reminders": list_reminders()})

@app.route("/api/reminders", methods=["GET"])
def api_list_reminders():
    return jsonify({"reminders": list_reminders()})

@app.route("/api/notes", methods=["POST"])
def api_add_note():
    data = request.json or {}
    content = data.get("content","")
    if not content:
        return jsonify({"error":"empty"}), 400
    add_note(content)
    return jsonify({"ok": True, "notes": list_notes()})

@app.route("/api/notes", methods=["GET"])
def api_list_notes():
    return jsonify({"notes": list_notes()})

@app.route("/api/water", methods=["POST"])
def api_set_water():
    data = request.json or {}
    date = data.get("date")
    count = int(data.get("count", 0))
    if not date:
        return jsonify({"error":"missing date"}), 400
    set_water_count(date, count)
    return jsonify({"ok": True, "count": count})

@app.route("/api/water", methods=["GET"])
def api_get_water():
    date = request.args.get("date")
    if not date:
        return jsonify({"error":"missing date"}), 400
    cur = get_water_count(date)
    return jsonify({"count": cur["count"] if cur else 0})

@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.json or {}
    msg = data.get("message","").strip()
    if not msg:
        return jsonify({"error":"empty"}), 400
    out = generate_text(msg)
    return jsonify({"reply": out})

@app.route("/api/summarize", methods=["POST"])
def api_summarize():
    data = request.json or {}
    txt = data.get("text","").strip()
    if not txt:
        return jsonify({"error":"empty"}), 400
    prompt = "Summarize the following medical report for a non-expert in 4 short bullet points and one short plain-language summary:\n\n" + txt
    out = generate_text(prompt)
    return jsonify({"summary": out})

@app.route("/api/upload_image", methods=["POST"])
def api_upload_image():
    if "image" not in request.files:
        return jsonify({"error": "no file"}), 400

    f = request.files["image"]
    name = secure_filename(f.filename)
    target = os.path.join(app.config["UPLOAD_FOLDER"], name)
    f.save(target)

    # Local analysis
    try:
        local_desc = image_describe(target)
    except Exception as e:
        logger.exception("Local image analysis failed: %s", e)
        local_desc = f"Local analysis error: {e}"

    # Gemini description (safe, non-diagnostic)
    gemini_desc = None
    if GENAI:
        try:
            prompt = safe_prefix() + "Describe visible patterns in this image in simple, non-expert terms. Do NOT provide any diagnosis. If something looks unusual, say it 'may appear unusual' and advise consulting a clinician."
            # Note: we reference that an image was uploaded to the server. If advanced SDK image input is available you can extend this.
            gemini_desc = gemini_generate(prompt + f"\n\n(Image was uploaded to server at: {target})")
        except Exception as e:
            logger.exception("Gemini vision error: %s", e)
            gemini_desc = f"Gemini vision error: {e}"
    else:
        gemini_desc = "Gemini not configured."

    return jsonify({
        "local_description": local_desc,
        "gemini_description": gemini_desc,
        "file": target
    })

@app.route("/api/analyze_local", methods=["POST"])
def api_analyze_local():
    data = request.json or {}
    path = data.get("path")
    if not path or not os.path.exists(path):
        return jsonify({"error":"path missing or not found"}), 400
    local_desc = image_describe(path)
    gemini_desc = "Gemini not configured."
    if GENAI:
        try:
            prompt = safe_prefix() + "Describe visible patterns in this image in simple, non-expert terms. Do NOT diagnose."
            gemini_desc = gemini_generate(prompt + f"\n\n(Image was available at: {path})")
        except Exception as e:
            gemini_desc = f"Gemini error: {e}"
    return jsonify({"local_description": local_desc, "gemini_description": gemini_desc})

@app.route("/api/daily_summary", methods=["GET"])
def api_daily_summary():
    notes = list_notes(limit=10)
    reminders = list_reminders()
    prompt = "Create a short daily summary (3-6 sentences) from these notes and reminders. Notes:\n"
    for n in notes:
        prompt += "- " + n["content"] + "\n"
    prompt += "\nReminders:\n"
    for r in reminders:
        prompt += "- " + r["name"] + " at " + r["time"] + "\n"
    prompt += "\nWrite a friendly daily summary and list one actionable tip."
    out = generate_text(prompt)
    return jsonify({"summary": out, "notes": notes, "reminders": reminders})

# ----- Startup -----
if __name__ == "__main__":
    init_db()
    logger.info("Medibot starting... DB at %s", DB_PATH)
    # For production use gunicorn (Procfile provided). Dev: run Flask built-in
    app.run(host="0.0.0.0", port=PORT)
